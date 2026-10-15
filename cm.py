# sidecar/cm.py —— 旁挂工具共用的最小 MCP 客户端（自己一份，不依赖小焦那边的代码）
#
# 为什么单独写一份：旁挂工具是「挂在小焦外面」的东西 —— 它的价值就是**不碰项目本身**。
# 如果它去 import 小焦的插件，那项目一挪位置/改结构就跟着坏，反而变成负担。
# 这里只做三件事：起进程 → initialize → tools/call（按行 JSON-RPC）。
import json
import os
import queue
import subprocess
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                       # 默认：引擎与本目录同级


def _find_exe():
    """找引擎可执行文件：环境变量 > 与仓库同级 > 几个常见位置 > 默认。

    【为什么要有"常见位置"这一段】实测：把仓库克隆到别处时，`ROOT/causal-memory.exe`
    自然不存在（引擎是另外下载的）。要么用户自己设 `CAUSAL_MEMORY_EXE`，
    要么我们把几个常见落点也找一遍 —— 后者能让"克隆下来就能跑"。
    """
    env = os.environ.get("CAUSAL_MEMORY_EXE")
    if env:
        return env
    cands = [
        os.path.join(ROOT, "causal-memory.exe"),
        os.path.join(ROOT, "causal-memory", "causal-memory.exe"),
        r"C:\xiaojiao\causal-memory\causal-memory.exe",
        os.path.join(os.path.expanduser("~"), "causal-memory", "causal-memory.exe"),
    ]
    for c in cands:
        if c and os.path.exists(c):
            return c
    return cands[0]        # 都没有就返回默认位置（错误信息里会带上它，方便对着改）


EXE = _find_exe()
DB = os.environ.get("CAUSAL_MEMORY_DB") or os.path.join(ROOT, "xiaojiao.db")
# 小焦项目目录（只读它的 self_learn 学习库与日志）
XIAOJIAO_DIRS = [p for p in (
    os.environ.get("XIAOJIAO_DIR"),
    r"C:\迅雷下载\xiaojiao-harnees-main",
    r"C:\xiaojiao\xiaojiao harness",
) if p and os.path.isdir(p)]


def engine_env():
    """交给引擎的环境：库路径 +（可选的）判官/嵌入配置。

    判官配置写在 `engine.env`（KEY=VALUE，一行一条）里，例如：
        CAUSAL_MEMORY_LLM_API=http://127.0.0.1:9292/v1
        CAUSAL_MEMORY_LLM_KEY=local
        CAUSAL_MEMORY_LLM_MODEL=xiaojiao
    有它就用自己的大脑当判官（判结果的成败/极性更准），没有就退化成正则式启发。
    """
    env = dict(os.environ)
    env["CAUSAL_MEMORY_DB"] = DB
    env.setdefault("PYTHONUTF8", "1")
    f = os.path.join(HERE, "engine.env")
    if os.path.exists(f):
        for line in open(f, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


class Client:
    """常驻的 MCP stdio 客户端。with Client() as c: c.call(...)"""

    def __init__(self, exe=None):
        self.exe = exe or EXE
        self.proc = None
        self._id = 0
        self._pending = {}
        self._lock = threading.Lock()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *a):
        self.stop()

    def start(self):
        if not os.path.exists(self.exe):
            raise RuntimeError("找不到 causal-memory 可执行文件：%s" % self.exe)
        self.proc = subprocess.Popen([self.exe], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
                                     errors="replace", bufsize=1, env=engine_env(),
                                     cwd=os.path.dirname(self.exe) or None)
        threading.Thread(target=self._read, daemon=True).start()
        self._call("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                  "clientInfo": {"name": "xiaojiao-sidecar", "version": "1"}}, 20)
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.proc.stdin.flush()
        return True

    def _read(self):
        try:
            for line in self.proc.stdout:
                line = (line or "").strip()
                if not line.startswith("{"):
                    continue
                try:
                    msg = json.loads(line)
                except Exception:
                    continue
                q = self._pending.get(msg.get("id"))
                if q is not None:
                    q.put(msg)
        except Exception:
            pass

    def _call(self, method, params=None, timeout=60):
        with self._lock:
            self._id += 1
            mid = self._id
            q = queue.Queue()
            self._pending[mid] = q
            self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": mid, "method": method,
                                              "params": params or {}}, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
            try:
                msg = q.get(timeout=timeout)
            finally:
                self._pending.pop(mid, None)
        if msg.get("error"):
            raise RuntimeError(str(msg["error"])[:200])
        return msg.get("result") or {}

    def call(self, tool, args, timeout=120):
        res = self._call("tools/call", {"name": tool, "arguments": args or {}}, timeout)
        txt = "\n".join(c.get("text", "") for c in (res.get("content") or [])
                        if isinstance(c, dict) and c.get("type") == "text")
        return txt.strip()

    def tools(self):
        return [t.get("name") for t in (self._call("tools/list", {}, 20).get("tools") or [])]

    def stop(self):
        try:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except Exception:
                    self.proc.kill()
        except Exception:
            pass
        self.proc = None


def record(c, decision, outcome, relation="caused", task_tag="小焦运维", context=None):
    """记一条「决策 → 结果」。**结果文案要带成功/失败字样** —— 引擎的极性判定靠它，
    不带的话这条边就是"other"，以后预警那一档永远不会亮（实测）。"""
    args = {"decision": decision, "outcome": outcome, "relation": relation, "task_tag": task_tag}
    if context:
        args["context"] = context
    return c.call("record_decision", args)


def find_xiaojiao():
    """找到小焦项目目录（只读用）。返回第一个能用的。"""
    alls = find_all_xiaojiao()
    return alls[0] if alls else None


def find_all_xiaojiao():
    """**所有**能找到的小焦目录（本机有两份副本，各自的学习库不一样 —— 都要读）。

    实测：迅雷那份学习库只有 8 条（新装的），工作目录那份有 414 条。
    只读第一份会把大头漏掉，所以这里返回全部，让调用方合并（去重靠内容指纹）。
    """
    out = []
    for d in XIAOJIAO_DIRS:
        if os.path.isdir(os.path.join(d, "self_learn")):
            p = os.path.join(d, "self_learn", "knowledge_vec.json")
            out.append((d, os.path.getsize(p) if os.path.exists(p) else 0))
    out.sort(key=lambda x: -x[1])          # 条目多的排前面
    return [d for d, _sz in out]
