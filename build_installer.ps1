param(
    [switch]$SkipAppBuild
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

Push-Location $root
try {
    if (-not $SkipAppBuild) {
        & (Join-Path $root "build.ps1")
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    $appExe = Join-Path $root "dist\livefreeze\livefreeze.exe"
    if (-not (Test-Path $appExe)) {
        throw "找不到 $appExe。请先构建应用，或移除 -SkipAppBuild。"
    }

    $isccCandidates = @(
        (Get-Command ISCC.exe -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -ErrorAction SilentlyContinue),
        "$env:LOCALAPPDATA\Programs\Inno\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }

    $iscc = $isccCandidates | Select-Object -First 1
    if (-not $iscc) {
        throw "未安装 Inno Setup 6。请执行：winget install JRSoftware.InnoSetup"
    }

    & $iscc (Join-Path $root "installer\livefreeze.iss")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

    Write-Host ""
    Write-Host "安装包已生成：" -ForegroundColor Green
    Write-Host "  installer\Output\LiveFreeze-Setup-0.2.0.exe"
} finally {
    Pop-Location
}
