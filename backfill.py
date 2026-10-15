# sidecar/backfill.py —— 把小焦**已有的历史经验**导进因果库（只读它的文件，不改它一行）
#
# 为什么要导：小焦的 `self_learn/knowledge_vec.json` 里已经有 400 多条「谁用了什么工具、成功还是失败」，
#   那正是「决策 → 结果」。不导的话因果库从零开始，等于把已经攒下的教训浪费掉。
#
# 用法：
#   python backfill.py            # 预演（只统计，不写库）
#   python backfill.py --apply    # 真写进因果库（幂等：导过的不会重复导）
#   python backfill.py --apply --limit 50
#
# ⚠️ 两条口径上的讲究（都影响以后能不能"预警"）：
#   ① 结果文案**必须带「成功：」或「失败：」**——引擎的极性判定就靠这个信号，
#      不带的话这条边极性是 other，`intervention_query` 永远回 UNKNOWN（实测）。
#   ② 决策文案要写成**动作**（"用「X」做 Y"），不要写成"用户问了什么"——
#      因为预警时候是拿"你打算做的动作"去比，比"用户的话"没有用。
import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cm  # noqa: E402

STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imported.json")


def load_state():
    try:
        return set(json.load(open(STATE, encoding="utf-8")))
    except Exception:
        return set()


def save_state(s):
    try:
        json.dump(sorted(s), open(STATE, "w", encoding="utf-8"), ensure_ascii=False)
    except Exception as e:
        print("（进度文件写不进去：%s）" % e)


def _h(*parts):
    return hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()[:16]


def _short(s, n=160):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[:n] + "…"


def parse_entry(text):
    """把一条学习库条目变成 (decision, outcome, relation, context) 或 None。

    实测看到两种形状（各占绝大多数）：
      工具类：`用户 <任务> → 小焦用「stealthy_fetch」成功 参数{…}：<结果摘要>`
      反思类：`反思: 用户问「…」，小焦答「…」，反馈「bad」。… 下次遇到此类问题应: …`
    解析不出来就**跳过并计数**（不硬凑一条假教训进库）。
    """
    t = (text or "").strip()
    if not t:
        return None
    # —— 工具类 ——
    m = re.match(r"^用户\s*(?P<task>.+?)\s*→\s*小焦用「(?P<tool>[^」]+)」\s*(?P<rest>.*)$", t, re.S)
    if m:
        task, tool, rest = _short(m.group("task"), 100), m.group("tool"), m.group("rest")
        ok = "成功" in rest[:20]
        bad = ("失败" in rest[:20]) or ("错误" in rest[:20]) or ("超时" in rest[:20])
        if not (ok or bad):
            return None
        decision = "用「%s」处理：%s" % (tool, task)
        # 结果里那串 `参数{…}：` 是给调试看的，留在库里只会让检索变吵 —— 去掉它，只留真实结果
        rest = re.sub(r"^\s*参数\s*\{.*?\}\s*[:：]?\s*", "", rest, flags=re.S)
        outcome = ("成功：" if ok else "失败：") + _short(re.sub(r"^(成功|失败)\s*", "", rest), 140)
        return decision, outcome, "caused", "来自小焦历史经验库（自动导入）"
    # —— 反思类 ——
    m = re.match(r"^反思[:：]\s*(?P<body>.+)$", t, re.S)
    if m:
        body = m.group("body")
        q = re.search(r"用户问「([^」]+)」", body)
        fb = re.search(r"反馈「([^」]+)」", body)
        fix = re.search(r"下次遇到此类问题应[:：]\s*(.+)$", body, re.S)
        if not (q and (fb or fix)):
            return None
        rate = (fb.group(1) if fb else "").strip()
        good = bool(re.search(r"good|5星|4星|3星|成功|对", rate))
        bad = bool(re.search(r"bad|1星|2星|失败|错|不行", rate))
        decision = "回答「%s」时按老一套来" % _short(q.group(1), 60)
        outcome = ("成功：" if good else ("失败：" if bad else "参考：")) + \
                  (_short(fix.group(1), 120) if fix else ("被反馈「%s」" % rate))
        return decision, outcome, "caused", "来自小焦反思记录（自动导入，反馈=%s）" % (rate or "无")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真写进因果库（默认只预演）")
    ap.add_argument("--limit", type=int, default=0, help="最多导多少条（0 = 全导）")
    ap.add_argument("--task-tag", default="小焦历史经验")
    a = ap.parse_args()

    xjs = cm.find_all_xiaojiao()
    if not xjs:
        print("❌ 没找到小焦项目目录（设 XIAOJIAO_DIR 环境变量，或把项目放回默认位置）")
        return 2
    entries = []          # (来源目录, 条目文本)
    for xj in xjs:
        p = os.path.join(xj, "self_learn", "knowledge_vec.json")
        if not os.path.exists(p):
            continue
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception as e:
            print("⚠️ 读不了 %s：%s" % (p, e))
            continue
        got = [str(x.get("text") or "") for x in (data.get("entries") or [])]
        print("小焦副本：%s —— 学习库 %d 条" % (xj, len(got)))
        entries += [(xj, t) for t in got]
    print("合计条目：%d 条（本机有多份副本时全部合并，重复的靠内容指纹去掉）" % len(entries))

    seen = load_state()
    rows, skipped, dup = [], 0, 0
    for src, text in entries:
        pr = parse_entry(text)
        if not pr:
            skipped += 1
            continue
        decision, outcome, relation, context = pr
        h = _h(decision, outcome)
        if h in seen:
            dup += 1
            continue
        rows.append((h, decision, outcome, relation, "%s（来源：%s）" % (context, os.path.basename(src))))
        seen.add(h)          # 同一次运行里也去重（两份副本会有一样的条目）
    if a.limit:
        rows = rows[:a.limit]

    print("能解析成「决策 → 结果」的：%d 条（解析不出跳过 %d 条，之前导过 %d 条）"
          % (len(rows), skipped, dup))
    print("\n前 5 条长这样：")
    for _h_, d, o, rel, _c in rows[:5]:
        print("  · %s\n    →(%s)→ %s" % (_short(d, 80), rel, _short(o, 80)))

    if not a.apply:
        print("\n（预演结束。要真写进因果库：加 --apply）")
        return 0

    ok = 0
    with cm.Client() as c:
        for h, d, o, rel, ctx in rows:
            try:
                c.call("record_decision", {"decision": d, "outcome": o, "relation": rel,
                                           "task_tag": a.task_tag, "context": ctx})
                seen.add(h)
                ok += 1
                if ok % 25 == 0:
                    print("  已导 %d/%d…" % (ok, len(rows)))
                    save_state(seen)
            except Exception as e:
                print("  ⚠️ 有一条没导进去：%s" % str(e)[:100])
    save_state(seen)
    print("\n✅ 导入完成：%d 条进了因果库（以后再跑不会重复导；进度记在 %s）" % (ok, STATE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
