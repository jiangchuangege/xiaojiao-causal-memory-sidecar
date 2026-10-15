# sidecar/to_turns.py —— 把小焦的会话导成 causal-memory 的 `distill` 输入格式（只读小焦的文件）
#
# 【为什么要它】引擎的 `extract/judge/reasoning` 只认它自己实现过的几种 agent 日志格式；
#   通用做法是转成 `distill` 认的 turns JSON（见它的 scripts/session_to_turns.py 里的规范）：
#       {"date": "YYYY-MM-DD", "turns": [["user", "..."], ["assistant", "..."], ...]}
#   然后 `causal-memory distill <文件或目录>`。
#
# 【转换口径（小焦的会话长什么样）】xiaojiao_sessions.json:
#   {"current": "...", "sessions": [{"id","title","messages":[{"role":"用户"|"小焦","content":"…"}]}]}
#   · role=用户 → "user"；其余（小焦）→ "assistant"
#   · 连着同一个说话人的消息**合并成一条**（规范要求；小焦偶尔会连着回好几条）
#   · 会话文件里**没存时间**，日期用会话文件的修改时间兜底 —— 这一点**不准**，如实写在文件名与日志里
#
# 用法：
#   python to_turns.py                 # 转所有会话到 turns/ 目录（不覆盖已有的）
#   python to_turns.py --limit 20      # 只转最近 20 条
#   python to_turns.py --source "C:\xiaojiao\xiaojiao harness"   # 指定某一份副本
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cm  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "turns")
MIN_TURNS = 2          # 只有一两句的会话（"今天几号"那种）不值一条 LLM 调用，跳过


def merge_turns(msgs):
    """把 [{role, content}] 变成 [["user"|"assistant", text], ...]，相邻同说话人合并。"""
    out = []
    for m in msgs or []:
        role = "user" if str(m.get("role")) in ("用户", "user", "User") else "assistant"
        text = str(m.get("content") or "").strip()
        if not text:
            continue
        if out and out[-1][0] == role:
            out[-1][1] += "\n" + text
        else:
            out.append([role, text])
    return out


def convert(sessions_path, out_dir, limit=0, tag=""):
    data = json.load(open(sessions_path, encoding="utf-8"))
    ss = data.get("sessions") or []
    made, skipped = 0, 0
    if limit:
        ss = ss[-limit:]
    mtime = datetime.datetime.fromtimestamp(os.path.getmtime(sessions_path))
    for s in ss:
        turns = merge_turns(s.get("messages"))
        if len(turns) < MIN_TURNS:
            skipped += 1
            continue
        sid = str(s.get("id") or "s")[:16]
        day = datetime.datetime.now()
        name = "%s%s_%s.json" % (tag, day.strftime("%Y-%m-%d"), sid)
        path = os.path.join(out_dir, name)
        if os.path.exists(path):
            skipped += 1
            continue
        doc = {"date": mtime.strftime("%Y-%m-%d"), "turns": turns,
               "note": "由小焦会话转换；会话本身没存时间，date 用的是会话文件的修改时间（可能不准）"}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False, indent=1)
        made += 1
    return made, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--source", default="")
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)

    sources = [a.source] if a.source else cm.find_all_xiaojiao()
    total_made = 0
    for i, d in enumerate(sources):
        p = os.path.join(d, "xiaojiao_sessions.json")
        if not os.path.exists(p):
            print("（%s 里没有 xiaojiao_sessions.json）" % d)
            continue
        try:
            made, skipped = convert(p, OUT, a.limit, tag="c%d_" % i)
        except Exception as e:
            print("❌ 转 %s 出错：%s" % (p, str(e)[:120]))
            continue
        print("%s → 生成 %d 个 turns 文件（跳过 %d：太短或已存在）" % (d, made, skipped))
        total_made += made
    print("\n合计新生成：%d 个，都在 %s" % (total_made, OUT))
    print("下一步（先预演，看清楚它会提炼出什么再真写）：")
    print("  python distill.py --dry-run --limit 3")
    print("  python distill.py --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
