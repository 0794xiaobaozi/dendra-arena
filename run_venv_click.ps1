$ErrorActionPreference = "Stop"
$logPath = Join-Path $PSScriptRoot "run_venv_click.log"

try {
    Set-Location $PSScriptRoot
    "=== $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===" | Out-File -FilePath $logPath -Encoding utf8 -Append
    "cwd=$PSScriptRoot" | Out-File -FilePath $logPath -Encoding utf8 -Append

    $python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    "python=$python" | Out-File -FilePath $logPath -Encoding utf8 -Append

    if (-not (Test-Path $python)) {
        Write-Host "Missing .venv environment." -ForegroundColor Red
        Write-Host "Run these first:" -ForegroundColor Yellow
        Write-Host "  py -3.11 -m venv .venv" -ForegroundColor White
        Write-Host "  .\.venv\Scripts\python.exe -m pip install -r requirements.txt" -ForegroundColor White
        "venv_missing" | Out-File -FilePath $logPath -Encoding utf8 -Append
    }
    else {
        Write-Host "Starting LiveFreeze..." -ForegroundColor Cyan
        & $python "$PSScriptRoot\main.py" 2>&1 | Tee-Object -FilePath $logPath -Append
        "exit_code=$LASTEXITCODE" | Out-File -FilePath $logPath -Encoding utf8 -Append
    }
}
catch {
    Write-Host "Start failed:" -ForegroundColor Red
    Write-Host $_ -ForegroundColor White
    $_ | Out-File -FilePath $logPath -Encoding utf8 -Append
}
finally {
    Write-Host ""
    Write-Host "Log file: $logPath" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
}
