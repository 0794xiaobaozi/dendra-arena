# 打包 LiveFreeze 为独立可运行文件夹（需先安装 PyInstaller）
# 用法：.\build.ps1
# 完成后在 dist\livefreeze\ 下得到 livefreeze.exe 及依赖，整份复制到其他电脑即可运行

$ErrorActionPreference = "Stop"
if (-not (Get-Command pixi -ErrorAction SilentlyContinue)) {
    Write-Host "未找到 Pixi，请先安装：winget install prefix-dev.pixi"
    exit 1
}
Push-Location $PSScriptRoot
try {
    pixi install
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    pixi run build
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "打包完成。将 dist\livefreeze 整个文件夹复制到其他电脑，运行 livefreeze.exe 即可。"
    }
} finally {
    Pop-Location
}
