$ErrorActionPreference = 'Stop'

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EnvFile = Join-Path $ProjectDir '.env'
if (-not (Test-Path $EnvFile)) {
    Write-Host '[autostart] .env not found -> skip'
    exit 0
}

$autoStart = 'false'
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^AUTO_START\s*=\s*(.+)$') {
        $autoStart = $Matches[1].Trim().ToLower()
    }
}

if ($autoStart -notin @('true','1','yes','on')) {
    Write-Host '[autostart] AUTO_START is not true -> skip'
    exit 0
}

$pythonPath = Join-Path $ProjectDir '.venv\Scripts\python.exe'
if (-not (Test-Path $pythonPath)) {
    Write-Host '[autostart] python in .venv not found -> skip'
    exit 0
}

$botPath = Join-Path $ProjectDir 'bot.py'
& $pythonPath $botPath
