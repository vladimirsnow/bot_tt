$ErrorActionPreference = 'Stop'

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

if (-not (Get-Command py -ErrorAction SilentlyContinue) -and -not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw 'Python is required (install Python 3.12+)'
}

$venvPy = Join-Path $ProjectDir '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3.12 -m venv .venv
    }
    else {
        & python -m venv .venv
    }
}

$venvPy = Join-Path $ProjectDir '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) {
    throw 'Failed to create venv'
}

& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -r requirements.txt

$envPath = Join-Path $ProjectDir '.env'
$envExample = Join-Path $ProjectDir '.env.example'
if (-not (Test-Path $envPath)) {
    Copy-Item $envExample $envPath
    Write-Host '.env created from .env.example'
}

$content = Get-Content $envPath
if (-not ($content | Where-Object { $_ -match '^AUTO_START\s*=' })) {
    Add-Content $envPath "`nAUTO_START=false"
    $content = Get-Content $envPath
}

$autoStart = 'false'
$content | ForEach-Object {
    if ($_ -match '^AUTO_START\s*=\s*(.+)$') {
        $autoStart = $Matches[1].Trim().ToLower()
    }
}

if ($autoStart -in @('true','1','yes','on')) {
    & (Join-Path $ProjectDir 'install_autostart_windows.ps1')
    Write-Host 'AUTO_START=true -> Windows autostart enabled'
}
else {
    & (Join-Path $ProjectDir 'uninstall_autostart_windows.ps1')
    Write-Host 'AUTO_START=false -> Windows autostart disabled'
}

Write-Host ''
Write-Host 'Done. Edit .env (BOT_TOKEN).'
Write-Host 'Start bot manually: .\.venv\Scripts\python.exe .\bot.py'
Write-Host 'After changing AUTO_START, rerun: .\bootstrap.ps1'
