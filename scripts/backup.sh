#!/usr/bin/env sh
# Пример ежедневной копии PostgreSQL. Каталог backup/ не коммитится.
set -e
mkdir -p backup
STAMP=$(date +%Y%m%d)
pg_dump "$DATABASE_URL" --format=custom --file="backup/iam-$STAMP.dump"
echo "Сохранено backup/iam-$STAMP.dump"
