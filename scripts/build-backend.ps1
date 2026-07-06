# 打包 arena 后端为独立 exe（one-file 构建）
# 用法: .\scripts\build-backend.ps1
# 输出: backend-dist\arena-backend.exe

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Push-Location $root
try {
    $dist = Join-Path $root "backend-dist"
    Remove-Item -Force "$dist\arena-backend.exe" -ErrorAction SilentlyContinue

    Write-Host "打包 arena 后端 (PyInstaller) ..." -ForegroundColor Cyan
    pixi run pyinstaller --noconfirm --clean --distpath $dist (Join-Path $root "backend" "backend.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失败" }

    # One-file build puts exe in workpath; copy to distpath
    $built = Join-Path $root "build" "backend" "arena-backend.exe"
    if (Test-Path $built) {
        Copy-Item $built $dist -Force
    }

    Write-Host ""
    Write-Host "后端打包完成: $dist\arena-backend.exe" -ForegroundColor Green
} finally {
    Pop-Location
}
