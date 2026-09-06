.PHONY: app build up down restart logs status test doctor clean

APP_URL := http://127.0.0.1:3000
API_URL := http://127.0.0.1:8000


app:
	@echo ""
	@echo "Bag Counter"
	@echo "Frontend: $(APP_URL)"
	@echo "Swagger:  $(API_URL)/docs"
	@echo ""
	@echo "Starting Docker Compose..."
	@echo ""
	docker compose up --build


build:
	docker compose build


up:
	docker compose up


down:
	docker compose down


restart:
	docker compose restart


status:
	docker compose ps


logs:
	docker compose logs -f


worker-logs:
	docker compose logs -f worker


api-logs:
	docker compose logs -f api


frontend-logs:
	docker compose logs -f frontend


test:
	uv run pytest -q


doctor:
	docker compose exec -T worker python -m scripts.check_runtime


clean:
	docker compose down --remove-orphans
