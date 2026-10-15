# sidecar/distill.py —— 让引擎从**真实会话**里提炼「决策 → 结果」（比手工记一条强得多）
#
# 它干的事：读 turns JSON（to_turns.py 生成的），用 LLM 一趟趟提炼，
#   把事实/偏好送进事实层、把教训与因果送进因果边。
#
# 用法：
#   python distill.py --dry-run --limit 3     # 只预演：看清楚它会提炼什么（不写库）
#   python distill.py --apply --limit 3       # 真写
#   python distill.py --apply                 # 全部（会调很多次模型，慢）
#
# ⚠️ 老实说三件事：
#   ① 它**每条会话都要调模型**（约每 15 条消息一次），本地 4B 跑起来慢，建议先 --limit 少量试；
#   ② 判官配置在 `engine.env`（默认指向你本机的 llama-swap 9292）；不配就退化成正则启发；
#   ③ 已经提炼过的会话记在 `distilled.json` 里，不会重复提炼（除非 --force）。
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cm  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
TURNS = os.path.join(HERE, "turns")
STATE = os.path.join(HERE, "distilled.json")


def load_state():
    try:
        return set(json.load(open(STATE, encoding="utf-8")))
    except Exception:
        return set()


def save_state(s):
    json.dump(sorted(s), open(STATE, "w", encoding="utf-8"), ensure_ascii=False)


def run_distill(path, extra=()):
    cmd = [cm.EXE, "distill", path] + list(extra)
    print("$ %s" % " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=cm.engine_env(),
                       cwd=os.path.dirname(cm.EXE) or None, timeout=1800)
    out = (r.stdout or "") + (r.stderr or "")
    print(out.strip()[:1500] or "（没有输出）")
    # ⚠️ 实测踩到：它**退出码是 0**，但正文里写着 "distill failed for …"（比如本地模型没起、
    #    超时）——只认退出码会把失败当成功、还把进度记上，下次不再重试。所以要读正文。
    failed = ("distill failed" in out) or ("error sending request" in out)
    return (1 if failed else r.returncode), out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真写进库（默认只预演）")
    ap.add_argument("--dry-run", action="store_true",
                    help="预演（不写库）。默认就是预演 —— 这个开关只是为了把意图写清楚")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--force", action="store_true", help="连提炼过的也再跑一遍")
    a = ap.parse_args()
    if a.dry_run:
        a.apply = False

    if not os.path.isdir(TURNS):
        print("❌ 还没有 turns 目录 —— 先跑 `python to_turns.py`")
        return 2
    files = sorted(f for f in os.listdir(TURNS) if f.endswith(".json"))
    seen = load_state()
    todo = [f for f in files if a.force or f not in seen]
    if a.limit:
        todo = todo[:a.limit]
    print("turns 文件 %d 个 ｜ 这次要提炼 %d 个 ｜ 模式：%s"
          % (len(files), len(todo), "真写" if a.apply else "预演（不写库）"))
    if not todo:
        print("（没有新会话要提炼）")
        return 0

    ok = 0
    for f in todo:
        p = os.path.join(TURNS, f)
        print("\n===== %s =====" % f)
        extra = ("--dry-run",) if not a.apply else ()
        code, out = run_distill(p, extra)
        if code == 0:
            ok += 1
            if a.apply:
                seen.add(f)
                save_state(seen)
        else:
            print("⚠️ 这个没成功（退出码 %d），不记进度，下次会再试" % code)
    print("\n完成：%d/%d" % (ok, len(todo)))
    if not a.apply:
        print("（预演模式：库没变。看清楚之后加 --apply 真写）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
