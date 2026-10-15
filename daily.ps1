# sidecar/daily.ps1 —— 因果记忆的日常保养（离线巩固 + 出日报）
#
# 为什么必须有人跑它：`sleep` 是引擎自己的"睡眠整理"——把 Q 值沿因果链回传、算衰减、清理、
#   挖相似/矛盾关系。不跑它，库里只是躺着不动，**不会自己变聪明**。
# 这个脚本只做两件事：跑一次 sleep、生成一份日报。不碰小焦项目里任何文件。
#
# 手动跑：  powershell -ExecutionPolicy Bypass -File daily.ps1
# 定时跑： 见 README.md 里的 schtasks 命令（本机已经注册好了）
$ErrorActionPreference = "Continue"
# 让重定向进日志的中文不乱码（Windows PowerShell 5.1 默认不是 UTF-8）
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
$exe  = Join-Path $root "causal-memory.exe"
$db   = Join-Path $root "xiaojiao.db"
$log  = Join-Path $root "reports\daily.log"

New-Item -ItemType Directory -Force -Path (Join-Path $root "reports") | Out-Null
$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path $log -Value "`n===== $ts 开始 =====" -Encoding UTF8

if (Test-Path $exe) {
    Add-Content -Path $log -Value "[1/2] 离线巩固（sleep）" -Encoding UTF8
    & $exe sleep --db $db *>> $log
} else {
    Add-Content -Path $log -Value "❌ 找不到 $exe" -Encoding UTF8
}

# 【2026-10-15 踩到】计划任务里跑的时候 PATH 跟你在终端里不一样 ——
#   直接写 `python` 会以"系统找不到指定的文件"(0x80070002) 失败。所以这里**找绝对路径**。
$py = $env:SIDECAR_PYTHON
if (-not $py -or -not (Test-Path $py)) {
    $cand = @("$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
              "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
              "C:\Python313\python.exe", "C:\Python312\python.exe")
    foreach ($c in $cand) { if (Test-Path $c) { $py = $c; break } }
}
if (-not $py -or -not (Test-Path $py)) {
    $w = (Get-Command python -ErrorAction SilentlyContinue)
    if ($w) { $py = $w.Source }
}
if (-not $py) { $py = "python" }   # 实在找不到就退回 PATH，并在日志里写清楚

Add-Content -Path $log -Value "[2/2] 生成日报（$py）" -Encoding UTF8
& $py (Join-Path $here "report.py") --quiet *>> $log
Add-Content -Path $log -Value "===== 结束 =====" -Encoding UTF8
