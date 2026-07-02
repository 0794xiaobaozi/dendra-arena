# 使用 Pixi 运行 LiveFreeze
# 首次运行前请执行: .\setup.ps1

if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    Write-Host "未检测到 pixi。请先安装: winget install prefix-dev.pixi" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path (Join-Path $PSScriptRoot ".pixi"))) {
    Write-Host "请先执行: .\setup.ps1" -ForegroundColor Red
    exit 1
}

pixi run run
