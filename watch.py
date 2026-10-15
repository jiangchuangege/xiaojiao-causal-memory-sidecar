# sidecar/watch.py —— 盯着小焦的学习库，把**新长出来的**经验持续导进因果库
#
# 为什么不改小焦也能做到：小焦每次自学习都会往 `self_learn/knowledge_vec.json` 里写条目
#   （那是它的既有行为，一个字节都不用动）。这个旁挂进程只做两件事：读那个文件、把新条目记进因果库。
#   于是"因果层跟着小焦一起长"，而项目本身毫发无损。
#
# 用法：
#   python watch.py                 # 前台跑（Ctrl+C 停）
#   python watch.py --interval 60   # 每 60 秒看一次（默认 60）
#   python watch.py --once          # 只看一次就退出（适合挂计划任务）
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import backfill  # noqa: E402  复用同一套解析口径（成功：/失败： 前缀 + 内容指纹去重）
import cm        # noqa: E402

TAG = os.environ.get("SIDECAR_TASK_TAG", "小焦运维")


def scan(client, seen):
    """扫一遍所有小焦副本的学习库，把没导过的导进去。返回这次导了几条。"""
    n = 0
    for xj in cm.find_all_xiaojiao():
        p = os.path.join(xj, "self_learn", "knowledge_vec.json")
        if not os.path.exists(p):
            continue
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception as e:      # 文件正被写坏/半写状态：这一轮跳过，下一轮再来
            print("（这一轮读不了 %s：%s）" % (p, str(e)[:60]))
            continue
        for it in (data.get("entries") or []):
            pr = backfill.parse_entry(str(it.get("text") or ""))
            if not pr:
                continue
            decision, outcome, relation, context = pr
            h = backfill._h(decision, outcome)
            if h in seen:
                continue
            try:
                client.call("record_decision", {"decision": decision, "outcome": outcome,
                                                "relation": relation, "task_tag": TAG,
                                                "context": context + "（旁挂增量导入）"})
                seen.add(h)
                n += 1
                print("  + %s →(%s)→ %s" % (backfill._short(decision, 60), relation,
                                            backfill._short(outcome, 60)))
            except Exception as e:
                print("  ⚠️ 有一条没导进去：%s" % str(e)[:100])
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=60)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args()

    seen = backfill.load_state()
    print("旁挂增量导入已启动 ｜ 间隔 %ds ｜ 库 %s" % (a.interval, cm.DB))
    print("盯着的小焦副本：%s" % (cm.find_all_xiaojiao() or "（一个都没找到）"))
    rounds = 0
    while True:
        try:
            with cm.Client() as c:
                n = scan(c, seen)
            if n:
                backfill.save_state(seen)
                print("[%s] 新增 %d 条" % (time.strftime("%H:%M:%S"), n))
            elif rounds % 20 == 0:
                print("[%s] 没有新条目（已跟踪 %d 条）" % (time.strftime("%H:%M:%S"), len(seen)))
        except Exception as e:
            print("[%s] 这一轮出错（下一轮再试）：%s" % (time.strftime("%H:%M:%S"), str(e)[:120]))
        rounds += 1
        if a.once:
            return 0
        time.sleep(max(10, a.interval))


if __name__ == "__main__":
    sys.exit(main())
