$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

foreach ($name in @("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy")) {
    Remove-Item "Env:$name" -ErrorAction SilentlyContinue
}

if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path .venv\Scripts\python.exe)) {
    python -m venv .venv
}

$python = ".\.venv\Scripts\python.exe"
& $python -c "import django" 2>$null
if ($LASTEXITCODE -ne 0) {
    & $python -m pip install -r requirements\dev.txt
}

& $python manage.py migrate
& $python manage.py seed_demo
Write-Host ""
Write-Host "Сайт:        http://127.0.0.1:8000/"
Write-Host "Django admin: http://127.0.0.1:8000/admin/    логин admin    пароль admin"
Write-Host "Аналитик:    analyst    пароль Analyst-IAM-2026!"
Write-Host "Остановка:   Ctrl+C"
Write-Host ""
Start-Job -ScriptBlock { Start-Sleep -Seconds 2; Start-Process "http://127.0.0.1:8000/" } | Out-Null
& $python manage.py runserver 127.0.0.1:8000
