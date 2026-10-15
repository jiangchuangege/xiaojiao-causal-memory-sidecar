# sidecar/report.py —— 因果库日报（只读库 + 只写自己的 reports/ 目录，不碰小焦项目）
#
# 看什么：这几天攒了多少教训、哪些动作"以前成功过"（可以放心复用）、
#   哪些"失败过"（动手前该看一眼）、以及引擎自己挖出来的矛盾/相似关系。
#
# 用法：
#   python report.py            # 打印到屏幕，并存一份到 reports/YYYY-MM-DD.md
#   python report.py --quiet    # 只存文件
import argparse
import datetime
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cm  # noqa: E402

REPORT_DIR = os.path.join(cm.ROOT, "reports")


def ask(c, tool, args):
    try:
        return c.call(tool, args) or ""
    except Exception as e:
        return "（%s 查询失败：%s）" % (tool, str(e)[:80])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    with cm.Client() as c:
        ledger = ask(c, "prediction_report", {})
        # 引擎没有"按极性列全部边"的工具，就用两个检索当抽样看：
        good = ask(c, "search_causal", {"query": "成功", "limit": 5})
        bad = ask(c, "search_causal", {"query": "失败 超时 报错 不可用", "limit": 5})
        patterns = ask(c, "search_patterns", {"limit": 8})
        dirinfo = ask(c, "causal_directory", {"limit": 1})

    now = datetime.datetime.now()
    lines = []
    lines.append("# 因果记忆日报 · %s" % now.strftime("%Y-%m-%d %H:%M"))
    lines.append("")
    lines.append("库：`%s`" % cm.DB)
    lines.append("")
    lines.append("## 库里现在有什么")
    lines.append("")
    lines.append("```")
    lines.append(dirinfo.strip()[:1200] or "（读不到）")
    lines.append("```")
    lines.append("")
    lines.append("## 成功的做法（抽样）")
    lines.append("")
    lines.append("```")
    lines.append(good.strip()[:1500] or "（还没有）")
    lines.append("```")
    lines.append("")
    lines.append("## 失败过的做法（动手前该看这些）")
    lines.append("")
    lines.append("```")
    lines.append(bad.strip()[:1500] or "（还没有）")
    lines.append("```")
    lines.append("")
    lines.append("## 引擎挖出来的关系（相似 / 矛盾）")
    lines.append("")
    lines.append("```")
    lines.append(patterns.strip()[:1200] or "（还没有）")
    lines.append("```")
    lines.append("")
    lines.append("## 预测账本（以前的判断押对了几成）")
    lines.append("")
    lines.append("```")
    lines.append(ledger.strip()[:1000] or "（还没有结算过）")
    lines.append("```")
    lines.append("")

    text = "\n".join(lines)
    os.makedirs(REPORT_DIR, exist_ok=True)
    out = os.path.join(REPORT_DIR, "%s.md" % now.strftime("%Y-%m-%d"))
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    if not a.quiet:
        print(text)
    print("（已存：%s）" % out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
