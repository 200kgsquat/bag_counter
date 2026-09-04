.PHONY: app build up down restart logs status worker-logs api-logs frontend-logs

app:
	docker compose up --build -d
	@echo ""
	@echo "Bag Counter is running"
	@echo "Frontend: http://127.0.0.1:3000"
	@echo "Swagger:  http://127.0.0.1:8000/docs"

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

logs:
	docker compose logs -f

worker-logs:
	docker compose logs -f worker

api-logs:
	docker compose logs -f api

frontend-logs:
	docker compose logs -f frontend

status:
	docker compose ps