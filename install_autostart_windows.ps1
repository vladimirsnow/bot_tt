$ErrorActionPreference = 'Stop'

$TaskName = 'TikTokReelsShortsBot'
$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$EntryScript = Join-Path $ProjectDir 'autostart_entry.ps1'

if (-not (Test-Path $EntryScript)) {
    throw "autostart_entry.ps1 not found: $EntryScript"
}

$cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$EntryScript`""

schtasks /Create /TN $TaskName /TR $cmd /SC ONLOGON /F | Out-Null
Write-Host "Windows autostart installed: $TaskName"
Write-Host "View task: schtasks /Query /TN $TaskName /V /FO LIST"
