# xiaojiao-causal-memory-sidecar

挂在小焦（[xiaojiao](https://github.com/jiangchuangege/xiaojiao-harness)）**外面**的
因果记忆保养工具。

它把小焦**已经攒下的**经验和会话导进
[causal-memory](https://github.com/JingxuanC/causal-memory)（一个 Rust 写的因果记忆引擎），
并每天做一次保养（极性回填 → 连链 → 图结构体检 → 发散评审 → 离线巩固 → 小批量提炼 → 导出 → 日报）。

**它不改小焦一行代码**：只**读**小焦的学习库（`self_learn/knowledge_vec.json`）、
会话（`xiaojiao_sessions.json`）、日志；写只写因果库和本目录的 `reports/`。
删掉这个目录，小焦一切照旧。

> 为什么单独一个仓库：它耦合的是 causal-memory 引擎，不是小焦本体。
> 放进小焦仓库会让主仓库变臃肿，引擎升级换目录时还得跟着改 —— 那不叫解耦。

## 它解决什么问题

小焦自己已经有记忆（事实/画像/经验），缺的是**因果教训**这一层：这个动作以前造成过什么后果、
这类事踩过什么坑。把这一层接上需要两半：

* **小焦那一半**（在 [小焦仓库](https://github.com/jiangchuangege/xiaojiao-harness) 里）：
  两个插件（16 个工具）+ 三类动作的自动埋点，属于小焦本体，跟着小焦走；
  说明见那边 `docs/causal-memory.md`；
* **这一半**（本仓库）：把**历史**喂进去、把**新会话**持续提炼进去、每天保养一次。
  属于"外面的工具"，跟着引擎走。

## 需要什么

| 依赖 | 说明 |
| --- | --- |
| causal-memory 引擎 | 从它的 [Releases](https://github.com/JingxuanC/causal-memory/releases) 下 `windows-x86_64` 包（约 5 MB，单二进制，**不需要 Rust 工具链**），解压到某目录 |
| Python 3.10+ | 只用标准库，**没有任何 pip 依赖** |
| 小焦（可选） | 想导历史/会话就得有它的目录；只想手动记也可以不用 |
| 一个 LLM（可选） | 判极性、提炼会话用。本机 llama-swap 的 OpenAI 兼容接口就行；不配则退回信号词启发式 |

## 快速开始

```powershell
# 1) 告诉它引擎在哪（默认找同目录的 causal-memory.exe，也可用环境变量）
$env:CAUSAL_MEMORY_EXE = "C:\xiaojiao\causal-memory\causal-memory.exe"
$env:CAUSAL_MEMORY_DB  = "C:\xiaojiao\causal-memory\xiaojiao.db"

# 2) 小焦在哪（默认自己找几个常见位置，也可以用环境变量指定）
$env:XIAOJIAO_DIR = "C:\迅雷下载\xiaojiao-harnees-main"

# 3) 判官配置（可选但推荐）
Copy-Item engine.env.example engine.env    # 然后按需改地址与模型名

# 4) 导历史经验（先预演，看清楚再真导）
python backfill.py
python backfill.py --apply

# 5) 会话 → turns → 提炼（先预演几条）
python to_turns.py
python distill.py --dry-run --limit 3
python distill.py --apply --limit 10

# 6) 增量导入跑一轮（不常驻）
python watch.py --once

# 7) 完整保养一把跑完（8 步）
powershell -ExecutionPolicy Bypass -File maintain.ps1
```

## 文件

| 文件 | 干什么 |
| --- | --- |
| `cm.py` | 共用的小客户端（MCP over stdio，自己一份，不依赖任何第三方库） |
| `backfill.py` | 把小焦学习库里的历史经验导进因果库（幂等，可预演） |
| `to_turns.py` | 把小焦的会话转成引擎认的 turns JSON |
| `distill.py` | 让引擎用 LLM 从会话里提炼「决策 → 结果」 |
| `watch.py` | 每轮扫学习库，增量导入新条目 |
| `maintain.ps1` | 完整保养八步（推荐） |
| `daily.ps1` | 简易版保养：只做 `sleep` + 日报（嫌八步太重就用这个） |
| `report.py` | 生成日报到 `reports/` |
| `engine.env.example` | 判官/超时配置模板（真的 `engine.env` 不入库） |

## 定时跑（Windows 计划任务）

```powershell
$side = (Get-Location).Path
$ps   = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$py   = (Get-Command python).Source

Register-ScheduledTask -TaskName "CausalDaily" `
  -Action (New-ScheduledTaskAction -Execute $ps -Argument "-ExecutionPolicy Bypass -File `"$side\maintain.ps1`"") `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 4am) -Force

Register-ScheduledTask -TaskName "CausalWatch" `
  -Action (New-ScheduledTaskAction -Execute $py -Argument "`"$side\watch.py`" --once") `
  -Trigger (New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(2) -RepetitionInterval (New-TimeSpan -Minutes 10)) -Force
```

## 实测踩到的四个坑（照抄进来就不必再踩）

1. **`--db` 认不认分两派**：`polarity`/`sleep`/`export`/`resolve-updates` 认；
   `link`/`refute` **不认**（传了当没看见，转头去开 `./.local/share/causal-memory/causal.db`，
   报 `Error code 14`）—— 但它们认环境变量 `CAUSAL_MEMORY_DB`，`maintain.ps1` 里先设好。
2. **计划任务里没有 PATH**：写 `python` 会以「系统找不到指定的文件」(0x80070002) 失败，必须绝对路径。
3. **`distill` 退出码是 0、正文却写着 `distill failed for …`**（通常是本地模型没起或超时）：
   只认退出码会把失败当成功，还会把进度记上。`distill.py` 现在读正文判成败；
   本地模型冷启动慢，`engine.env.example` 里把 `CAUSAL_MEMORY_HTTP_TIMEOUT_SECS` 设成了 900。
4. **`refute` 在千条边规模上会 panic**（退出码 101）—— 这是**引擎自己的 bug**（它目前是 0.9.3 alpha），
   本项目没有去改它的代码，只是不依赖它；失败不影响后面几步。

## 实测到的东西（本机一次真实运行的数字）

* 只接插件、没导历史：库里 6 条边，动手前预警基本回 `UNKNOWN`（等于没有预警）；
* 导入 414 条历史经验后：**600+ 条活跃因果边**、300+ 条引擎自己挖出来的关系、100+ 条事实；
  动作匹配上"历史上成功过" → `✅ SAFE`，匹配上"历史上失败过" → `⚠️ DANGER`；
* 529 个会话转成 turns，每天自动提炼 5 条（慢慢吃完，不占满显卡）。

**不粉饰的部分**：用本地 4B 当判官时，它常在 JSON 后面多写一段解释导致引擎解析失败，
退回信号词启发式（判成 `neutral`）—— 极性还不是条条都准；没配 embeddings 就只有 BM25，
没有语义检索。

## 隐私

`turns/`（从小焦会话转出来的对话）、`reports/`（含库快照导出）、`imported.json` / `distilled.json`
都在 `.gitignore` 里 —— **它们装的是你自己的数据，永远不进仓库**。

## 许可

MIT，见 [LICENSE](LICENSE)。
