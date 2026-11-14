# starts the app and the cloudflare tunnel so moneysprout.renengine.com works
# run from the project folder:  .\start-moneysprout.ps1

$Root = $PSScriptRoot
Set-Location $Root

if (!(Test-Path "$Root\venv\Scripts\python.exe")) {
    Write-Host "No venv found. Run: python -m venv venv ; venv\Scripts\activate ; pip install -r requirements.txt"
    exit 1
}
if (!(Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "cloudflared is not installed. Run: winget install Cloudflare.cloudflared"
    exit 1
}
if (Select-String -Path "$Root\cloudflare\config.yml" -Pattern "CHANGE-ME" -Quiet) {
    Write-Host "Fill in cloudflare\config.yml first (tunnel id and credentials file). See the README."
    exit 1
}

$env:COOKIE_SECURE = "true"
$env:PUBLIC_HOST = "moneysprout.renengine.com"

Write-Host "Starting app..."
# bound to loopback only, the tunnel is how people reach it
$app = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$Root\backend" `
    -FilePath "$Root\venv\Scripts\python.exe" `
    -ArgumentList "-m","uvicorn","main:app","--host","127.0.0.1","--port","8000","--proxy-headers","--forwarded-allow-ips","127.0.0.1","--no-server-header"

Start-Sleep -Seconds 2

Write-Host "Starting tunnel..."
try {
    cloudflared tunnel --config "$Root\cloudflare\config.yml" run
}
finally {
    # tunnel stopped, stop the app too
    if ($app -and !$app.HasExited) { Stop-Process -Id $app.Id -Force }
}
