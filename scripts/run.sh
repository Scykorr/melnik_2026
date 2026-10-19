#!/usr/bin/env sh
set -e
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then cp .env.example .env; fi
if [ ! -d .venv ]; then python3 -m venv .venv; fi
. .venv/bin/activate
python -m pip install -r requirements/dev.txt
python manage.py migrate
python manage.py seed_demo
echo "Откройте http://127.0.0.1:8000/  логин analyst  пароль Analyst-IAM-2026!"
python manage.py runserver 127.0.0.1:8000
