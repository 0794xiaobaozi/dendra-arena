$ErrorActionPreference = "Stop"

$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "未找到 .venv 环境。" -ForegroundColor Red
    Write-Host "请先在项目目录执行：" -ForegroundColor Yellow
    Write-Host "  py -3.11 -m venv .venv" -ForegroundColor White
    Write-Host "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt" -ForegroundColor White
    exit 1
}

& $python "$PSScriptRoot\main.py"
