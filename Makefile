.PHONY: app build up down restart logs status test doctor clean

APP_URL := http://127.0.0.1:3000
API_URL := http://127.0.0.1:8000


app:
	docker compose up --build -d --remove-orphans --force-recreate --wait
	@echo ""
	@echo "Bag Counter is ready"
	@echo "Frontend: $(APP_URL)"
	@echo "Swagger:  $(API_URL)/docs"


build:
	docker compose build


up:
	docker compose up -d --wait


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
	docker compose exec -T worker python -c "import os, torch, mmcv, mmdet; assert os.path.isfile('/app/checkpoints/bag_detector.pth'); assert torch.cuda.is_available(); print('GPU:', torch.cuda.get_device_name(0)); print('MMCV:', mmcv.__version__); print('MMDetection:', mmdet.__version__)"


clean:
	docker compose down --remove-orphans