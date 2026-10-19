# ИАМ «Регион»

Разработка автоматизированной системы мониторинга протестной активности населения для подготовки ИАМ «Регион».

Это локальный MVP. Он разбирает открытые публикации на уровне событий, тем, периодов и территорий. Система не идентифицирует участников, не распознаёт лица, не строит социальные графы и не делает индивидуальные политические профили. Демонстрационные данные синтетические. Показатели T0, T1 и K_T до реального эксперимента отображаются как «не измерено».

## Стек

Локальное окружение этого репозитория: Python 3.14.7 и Django 5.2.18. Образ Docker и проверка GitHub Actions используют Python 3.13, ту же ветку Django 5.2 LTS. PostgreSQL 17 и Redis 7 поднимаются через Compose. Для запуска без Docker по умолчанию используется SQLite, а задачи Celery выполняются сразу в процессе.

Зафиксированные версии лежат в `requirements/base.txt` и `requirements/dev.txt`. На машине разработки нет Node.js, поэтому стили собраны локальным файлом `static/css/app.css`. Скрипты HTMX, Alpine.js и ECharts лежат в `static/vendor/`, шрифт интерфейса — в `static/fonts/DejaVuSans.ttf`. Страницы не обращаются к CDN. Файлы Django admin отдаёт само приложение из установленного пакета. Токены интерфейса: фон slate, акцент глубокий синий, радиус 12 px.

## Запуск без Docker

Windows: дважды щёлкните `start.bat` в корне проекта.

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run.ps1
```

Linux или macOS:

```sh
bash scripts/run.sh
```

Вручную:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements\dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py seed_demo
.\.venv\Scripts\python.exe manage.py runserver
```

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements/dev.txt
cp .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```

Откройте http://127.0.0.1:8000/

## Запуск в Docker

```sh
cp .env.example .env
docker compose up -d --build
docker compose exec web python manage.py seed_demo
```

Эквивалент Makefile: `make up`, `make seed`, `make test`, `make lint`, `make down`. На Windows без `make` используйте те же команды `docker compose` и `python manage.py`.

Профиль Nginx: `docker compose --profile production up -d`.

## Демонстрационные учётные записи

Пароли только для локального стенда. Все записи синтетические.

| Логин | Пароль | Роль |
| --- | --- | --- |
| admin | admin | администратор, в том числе Django admin `/admin/` |
| operator | Operator-IAM-2026! | оператор |
| analyst | Analyst-IAM-2026! | аналитик |
| approver | Approver-IAM-2026! | согласующий |
| auditor | Auditor-IAM-2026! | аудитор |

## Проверки

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe manage.py readycheck
```

Сценарий «вход → сводка → очередь → карточка → подтверждение → проект отчёта» покрыт тестом Django. Отдельный файл Playwright пропускается, если пакет браузера не установлен.

## Переменные среды

Смотрите `.env.example`. Секреты не хранятся в репозитории. `DATABASE_URL` может указывать на SQLite или PostgreSQL. Пустой `REDIS_URL` включает локальный кэш и немедленное выполнение Celery. `URL_ALLOWLIST` дополнительно ограничивает ручные ссылки. `SECRET_KEY` в production не может оставаться значением-заглушкой.

## Что входит в MVP и что является исследованием

В MVP: роли, источники, RSS/Atom, импорт JSON/CSV, ручная ссылка с защитой от SSRF, дедупликация, очередь событий, ИПА, сводка, конструктор ИАМ, экспорт DOCX/PDF, аудит, API и журнал экспериментов без вымышленных замеров.

Исследовательский контур не показывает фактические F1 и K_T, пока нет внешнего эталона и завершённых сопоставимых сессий. Семантические эмбеддинги выключены, пока не установлена локальная модель. Базовый метод TF-IDF работает сам.

## Ограничения

Индекс описывает открытый информационный поток, а не взгляды жителей. Неподтверждённые события в индекс и в ИАМ не попадают. Утверждённую версию отчёта нельзя изменить. Карантин не создаёт подтверждённое событие. Обход авторизации, CAPTCHA и ограничений сайта не реализован.
