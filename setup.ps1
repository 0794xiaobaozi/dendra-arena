# LiveFreeze 环境搭建（使用 Pixi）
# 在项目目录下执行: .\setup.ps1
# 需先安装 Pixi: https://pixi.sh/latest/installation/

$ErrorActionPreference = "Stop"

if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    Write-Host "未检测到 pixi。请先安装 Pixi：" -ForegroundColor Red
    Write-Host "  winget install prefix-dev.pixi" -ForegroundColor White
    Write-Host "  或访问 https://pixi.sh/latest/installation/" -ForegroundColor White
    exit 1
}

Write-Host "正在安装依赖 (pixi install) ..." -ForegroundColor Cyan
pixi install
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host ""
Write-Host "完成。运行程序：" -ForegroundColor Green
Write-Host "  pixi run run" -ForegroundColor White
Write-Host "或进入环境后运行：" -ForegroundColor Green
Write-Host "  pixi shell" -ForegroundColor White
Write-Host "  python main.py" -ForegroundColor White
