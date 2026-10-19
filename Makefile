.PHONY: up down test lint seed
up:
	docker compose up -d --build
down:
	docker compose down
test:
	pytest
lint:
	ruff check .
	mypy
seed:
	python manage.py migrate && python manage.py seed_demo
