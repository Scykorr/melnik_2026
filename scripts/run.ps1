$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path .venv\Scripts\python.exe)) { python -m venv .venv }
.\.venv\Scripts\python.exe -m pip install -r requirements\dev.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
Write-Host "Откройте http://127.0.0.1:8000/  логин analyst  пароль Analyst-IAM-2026!"
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
