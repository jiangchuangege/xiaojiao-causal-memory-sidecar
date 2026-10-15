# sidecar/maintain.ps1 —— 因果记忆的完整保养（一把跑完，不碰小焦项目里任何文件）
#
# 顺序有讲究（每一步都用得到上一步的结果）：
#   1) polarity        结果极性回填（成败/好坏）——后面预警分档靠它
#   2) link            把零散的决策连成多跳链（"崩 ← OOM ← 缓存没 TTL"这种）
#   3) refute          图结构体检：找出疑似伪因果（5 道 refuter）
#   4) resolve-updates LLM 评审"同一决策反复记、结局却不同"的发散项
#   5) sleep           离线巩固：Q 值回传 / 衰减 / 挖相似与矛盾
#   6) distill 小批量   从真实会话里提炼决策与结果（每次只跑几条，慢慢吃完，不占满显卡）
#   7) export          导出一份快照（备份 + 可分享），存 reports/
#   8) report          出一份人能看的日报
#
# 手动：powershell -ExecutionPolicy Bypass -File maintain.ps1
# 定时：已注册为 XiaojiaoCausalDaily（每天 04:00）
$ErrorActionPreference = "Continue"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$exe  = Join-Path $root "causal-memory.exe"
$db   = Join-Path $root "xiaojiao.db"
$rep  = Join-Path $root "reports"
$log  = Join-Path $rep "maintain.log"
New-Item -ItemType Directory -Force -Path $rep | Out-Null

# 引擎自己的判官/超时配置（engine.env）
Get-Content (Join-Path $here "engine.env") -Encoding UTF8 -ErrorAction SilentlyContinue | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
        $kv = $line.Split("=", 2)
        [Environment]::SetEnvironmentVariable($kv[0].Trim(), $kv[1].Trim(), "Process")
    }
}

# python 的绝对路径（计划任务里 PATH 不一样，写 `python` 会 0x80070002 失败）
$py = $env:SIDECAR_PYTHON
if (-not $py -or -not (Test-Path $py)) {
    foreach ($c in @("$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
                     "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe")) {
        if (Test-Path $c) { $py = $c; break }
    }
}
if (-not $py) { $py = "python" }

function Step($n, $title, $block) {
    Add-Content -Path $log -Value "`n--- [$n] $title  $(Get-Date -Format 'HH:mm:ss')" -Encoding UTF8
    # ⚠️ 不能直接 `*>> $log`：Windows PowerShell 5.1 把**外部程序**的输出按 UTF-16 写进文件，
    #    日志里中文全变成"字 符 间 隔"那副样子（实测）。改成先收进变量、再按 UTF-8 追加。
    $out = & $block 2>&1 | Out-String
    if ($out.Trim()) { Add-Content -Path $log -Value $out.Trim() -Encoding UTF8 }
    Add-Content -Path $log -Value "    (退出码 $LASTEXITCODE)" -Encoding UTF8
}

Add-Content -Path $log -Value "`n================ $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ================" -Encoding UTF8

if (-not (Test-Path $exe)) {
    Add-Content -Path $log -Value "❌ 找不到引擎：$exe" -Encoding UTF8
    exit 1
}

# ⚠️ 引擎的子命令在"库路径"上分两派（实测踩到）：
#   · `polarity` / `sleep` / `export` / `resolve-updates` —— 认 `--db`；
#   · `link` / `refute` —— **不认 `--db`**（传了当没看见，转头去开 .\.local/share/… 报 Error code 14），
#     但它们**认环境变量 `CAUSAL_MEMORY_DB`**。所以先把环境变量设好，这两条不带参数跑。
$env:CAUSAL_MEMORY_DB = $db
Step 1 "结果极性回填"      { & $exe polarity --db $db }
Step 2 "把决策连成多跳链"   { & $exe link }
Step 3 "图结构体检（伪因果）" { & $exe refute }
Step 4 "发散项评审（LLM）"   { & $exe resolve-updates --db $db }
Step 5 "离线巩固（sleep）"   { & $exe sleep --db $db }
Step 6 "会话提炼（小批量 5 条）" { & $py (Join-Path $here "distill.py") --apply --limit 5 }
Step 7 "导出快照"          { & $exe export (Join-Path $rep ("export-" + (Get-Date -Format "yyyyMMdd") + ".jsonl")) --db $db }
Step 8 "生成日报"          { & $py (Join-Path $here "report.py") --quiet }

Add-Content -Path $log -Value "================ 结束 ================" -Encoding UTF8
