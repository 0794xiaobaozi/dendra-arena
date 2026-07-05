# 打包 arena 后端为独立 exe
# 用法: .\scripts\build-backend.ps1
# 输出: backend-dist\arena-backend\arena-backend.exe

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Push-Location $root
try {
    $dist = Join-Path $root "backend-dist"
    Remove-Item -Recurse -Force $dist -ErrorAction SilentlyContinue

    Write-Host "打包 arena 后端 (PyInstaller) ..." -ForegroundColor Cyan
    & pixi run --environment default pyinstaller --noconfirm --clean --distpath $dist (Join-Path $root "backend" "backend.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败" }

    Write-Host ""
    Write-Host "后端打包完成: $dist\arena-backend\arena-backend.exe" -ForegroundColor Green
} finally {
    Pop-Location
}
