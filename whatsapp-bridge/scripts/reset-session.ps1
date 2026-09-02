# Stop bridge + Chrome, delete WhatsApp session (requires QR scan on next start).
Get-CimInstance Win32_Process -Filter "Name='node.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -match 'whatsapp-bridge|src\\index\.js' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" -ErrorAction SilentlyContinue |
  Where-Object { $_.CommandLine -like '*wwebjs_auth*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$bridge = Split-Path $PSScriptRoot -Parent
$auth = Join-Path $bridge '.wwebjs_auth'
$pidFile = Join-Path $bridge '.bridge.pid'

if (Test-Path $pidFile) { Remove-Item $pidFile -Force }
if (Test-Path $auth) {
  Remove-Item $auth -Recurse -Force
  Write-Host "[bridge] deleted .wwebjs_auth — next start will show QR code"
} else {
  Write-Host "[bridge] no session folder found"
}

Write-Host "[bridge] run: fnm use 20 && npm start"
