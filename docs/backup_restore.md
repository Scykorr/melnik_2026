# Резервное копирование и восстановление

Для production-примера копируется база PostgreSQL, не каталог медиа с секретами.

Создание копии описано в `scripts/backup.sh` и `scripts/backup.ps1`. Файл `backup/iam-ГГГГММДД.dump` хранится вне git.

Восстановление на чистую базу:

```sh
pg_restore --clean --if-exists --dbname "$DATABASE_URL" backup/iam-ДАТА.dump
python manage.py migrate
python manage.py readycheck
```

SQLite: остановить сервер, заменить `db.sqlite3` сохранённой копией, снова запустить сервер.

Команда `purge_derived` удаляет старые агрегаты и черновики и пишет в журнал только счётчики и основание, без текста публикаций. Утверждённые отчёты она не трогает.
