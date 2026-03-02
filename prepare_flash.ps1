$ErrorActionPreference = 'Stop'

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectDir

# Runtime-only artifacts: remove before copying to USB.
if (Test-Path '.venv') { Remove-Item '.venv' -Recurse -Force }

Get-ChildItem -Path . -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
  ForEach-Object { Remove-Item $_.FullName -Recurse -Force }

Get-ChildItem -Path . -Recurse -File -Include '*.pyc','*.pyo','*.log' -ErrorAction SilentlyContinue |
  ForEach-Object { Remove-Item $_.FullName -Force }

if (Test-Path 'downloads') {
  Get-ChildItem -Path 'downloads' -Force -ErrorAction SilentlyContinue |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force }
}
else {
  New-Item -ItemType Directory -Path 'downloads' | Out-Null
}

Write-Host 'Project is cleaned for USB transfer.'
Write-Host 'Next on another PC: run ./bootstrap.sh (Linux) or .\bootstrap.ps1 (Windows).'
