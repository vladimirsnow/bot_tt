$ErrorActionPreference = 'Stop'

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

$envFile = Join-Path $ProjectDir '.env'
$envExample = Join-Path $ProjectDir '.env.example'
if (-not (Test-Path $envFile)) {
    if (-not (Test-Path $envExample)) {
        throw 'Missing .env and .env.example'
    }
    Copy-Item $envExample $envFile
}

$lines = @()
if (Test-Path $envFile) {
    $lines = Get-Content $envFile
}

$updated = $false
for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^AUTO_START\s*=') {
        $lines[$i] = 'AUTO_START=true'
        $updated = $true
    }
}
if (-not $updated) {
    $lines += 'AUTO_START=true'
}
Set-Content -Path $envFile -Value $lines -Encoding UTF8

$bootstrap = Join-Path $ProjectDir 'bootstrap.ps1'
if (-not (Test-Path $bootstrap)) {
    throw "bootstrap.ps1 not found: $bootstrap"
}

& $bootstrap *> $null

$taskName = 'TikTokReelsShortsBot'
schtasks /Query /TN $taskName *> $null
if ($LASTEXITCODE -eq 0) {
    schtasks /Run /TN $taskName *> $null
    Write-Host 'Bot started in background via Windows Task Scheduler.'
    exit 0
}

$pythonw = Join-Path $ProjectDir '.venv\Scripts\pythonw.exe'
$python = Join-Path $ProjectDir '.venv\Scripts\python.exe'
$botPath = Join-Path $ProjectDir 'bot.py'

if (Test-Path $pythonw) {
    Start-Process -FilePath $pythonw -ArgumentList "`"$botPath`"" -WindowStyle Hidden
    Write-Host 'Bot started hidden via pythonw.'
    exit 0
}

if (Test-Path $python) {
    Start-Process -FilePath $python -ArgumentList "`"$botPath`"" -WindowStyle Hidden
    Write-Host 'Bot started hidden via python.exe.'
    exit 0
}

throw 'Python executable not found in .venv\Scripts'
