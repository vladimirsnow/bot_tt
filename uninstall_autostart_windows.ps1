$ErrorActionPreference = 'Continue'
$TaskName = 'TikTokReelsShortsBot'

schtasks /Delete /TN $TaskName /F | Out-Null
Write-Host "Windows autostart removed: $TaskName"
