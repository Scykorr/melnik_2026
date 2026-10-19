$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path backup | Out-Null
$stamp = Get-Date -Format "yyyyMMdd"
if (-not $env:DATABASE_URL) { throw "Задайте DATABASE_URL для PostgreSQL" }
pg_dump $env:DATABASE_URL --format=custom --file "backup/iam-$stamp.dump"
Write-Host "Сохранено backup/iam-$stamp.dump"
