#!/usr/bin/env sh
set -e
cd "$(dirname "$0")/.."
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy
if [ ! -f .env ]; then cp .env.example .env; fi
if [ ! -d .venv ]; then python3 -m venv .venv; fi
. .venv/bin/activate
if ! python -c "import django" >/dev/null 2>&1; then
  python -m pip install -r requirements/dev.txt
fi
python manage.py migrate
python manage.py seed_demo
echo ""
echo "Сайт:         http://127.0.0.1:8000/"
echo "Django admin: http://127.0.0.1:8000/admin/    логин admin    пароль admin"
echo "Аналитик:     analyst    пароль Analyst-IAM-2026!"
echo "Остановка:    Ctrl+C"
echo ""
python manage.py runserver 127.0.0.1:8000
