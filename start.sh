#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

FRONTEND_URL="http://127.0.0.1:3000"
FRONTEND_HEALTH_URL="http://127.0.0.1:3000/api/health"
API_HEALTH_URL="http://127.0.0.1:8000/health"

CHECKPOINT_DIR="$ROOT_DIR/checkpoints"
CHECKPOINT_PATH="$CHECKPOINT_DIR/bag_detector.pth"
CHECKPOINT_TMP="$CHECKPOINT_PATH.part"

CHECKPOINT_URL="${BAG_COUNTER_CHECKPOINT_URL:-https://github.com/200kgsquat/bag_counter/releases/latest/download/bag_detector.pth}"


step() {
    echo
    echo "============================================================"
    echo "  $1"
    echo "============================================================"
    echo
}


ok() {
    echo "[OK] $1"
}


fail() {
    echo "[ERROR] $1"
    exit 1
}


wait_http() {
    local url="$1"
    local attempts="${2:-60}"

    for ((i=1; i<=attempts; i++)); do
        if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
            echo
            return 0
        fi

        printf "."
        sleep 2
    done

    echo
    return 1
}


echo
echo "============================================================"
echo "                  BAG COUNTER STARTER"
echo "============================================================"
echo


# ------------------------------------------------------------
# Docker
# ------------------------------------------------------------

step "Checking Docker"

command -v docker >/dev/null 2>&1 || \
    fail "Docker is not installed."


if ! docker info >/dev/null 2>&1; then
    echo "Docker daemon is not running."

    if command -v systemctl >/dev/null 2>&1; then
        echo "Trying to start Docker..."

        sudo systemctl start docker || \
            fail "Could not start Docker."
    else
        fail "Start the Docker daemon and run this script again."
    fi
fi

docker info >/dev/null 2>&1 || \
    fail "Docker daemon is unavailable."

ok "Docker is running"


# ------------------------------------------------------------
# Docker Compose
# ------------------------------------------------------------

step "Checking Docker Compose"

docker compose version >/dev/null 2>&1 || \
    fail "Docker Compose plugin is not available."

ok "Docker Compose is available"


# ------------------------------------------------------------
# Checkpoint
# ------------------------------------------------------------

step "Checking ML model checkpoint"

mkdir -p "$CHECKPOINT_DIR"

if [[ -f "$CHECKPOINT_PATH" ]] && \
   [[ $(stat -c%s "$CHECKPOINT_PATH") -gt 1048576 ]]; then

    SIZE_MB=$(du -m "$CHECKPOINT_PATH" | cut -f1)
    ok "Checkpoint found (${SIZE_MB} MB)"

else
    echo "Checkpoint not found."
    echo "Downloading model..."

    rm -f "$CHECKPOINT_TMP"

    if command -v curl >/dev/null 2>&1; then
        curl -fL \
            "$CHECKPOINT_URL" \
            -o "$CHECKPOINT_TMP"

    elif command -v wget >/dev/null 2>&1; then
        wget \
            "$CHECKPOINT_URL" \
            -O "$CHECKPOINT_TMP"

    else
        fail "Neither curl nor wget is installed."
    fi


    [[ -f "$CHECKPOINT_TMP" ]] || \
        fail "Checkpoint download failed."


    SIZE=$(stat -c%s "$CHECKPOINT_TMP")

    [[ "$SIZE" -gt 1048576 ]] || {
        rm -f "$CHECKPOINT_TMP"
        fail "Downloaded checkpoint looks invalid."
    }


    mv "$CHECKPOINT_TMP" "$CHECKPOINT_PATH"

    ok "Checkpoint downloaded"
fi


# ------------------------------------------------------------
# Start containers
# ------------------------------------------------------------

step "Building and starting Bag Counter"

docker compose up \
    --build \
    -d \
    --remove-orphans \
    --force-recreate

ok "Docker Compose finished"


# ------------------------------------------------------------
# API
# ------------------------------------------------------------

step "Waiting for FastAPI"

if ! wait_http "$API_HEALTH_URL" 90; then
    docker compose logs --tail=100 api
    fail "FastAPI did not become healthy."
fi

ok "FastAPI is healthy"


# ------------------------------------------------------------
# Refresh frontend
# ------------------------------------------------------------

step "Refreshing frontend proxy"

docker compose restart frontend

sleep 2

ok "Frontend proxy restarted"


# ------------------------------------------------------------
# Worker
# ------------------------------------------------------------

step "Checking ML worker"

if ! docker compose ps \
    --services \
    --status running \
    | grep -qx "worker"; then

    docker compose logs --tail=100 worker
    fail "Celery worker is not running."
fi

ok "Celery worker is running"


# ------------------------------------------------------------
# ML runtime / CUDA
# ------------------------------------------------------------

step "Checking ML runtime and GPU"

docker compose exec -T worker python -c "
import os
import sys
import cv2
import torch
import mmcv
import mmdet

checkpoint = '/app/checkpoints/bag_detector.pth'

assert os.path.isfile(checkpoint), \
    f'Checkpoint not visible: {checkpoint}'

assert torch.cuda.is_available(), \
    'CUDA is not available inside worker'

print('Python:', sys.version.split()[0])
print('OpenCV:', cv2.__version__)
print('MMCV:', mmcv.__version__)
print('MMDetection:', mmdet.__version__)
print('CUDA available:', torch.cuda.is_available())
print('GPU:', torch.cuda.get_device_name(0))
print('Checkpoint:', checkpoint)
" || {
    docker compose logs --tail=100 worker
    fail "ML runtime check failed."
}

ok "ML worker and GPU are ready"


# ------------------------------------------------------------
# Frontend
# ------------------------------------------------------------

step "Waiting for frontend"

if ! wait_http "$FRONTEND_HEALTH_URL" 45; then
    docker compose logs --tail=100 frontend
    fail "Frontend did not become healthy."
fi

ok "Frontend is ready"


# ------------------------------------------------------------
# Done
# ------------------------------------------------------------

step "Bag Counter is ready"

docker compose ps

echo
echo "Frontend:"
echo "  $FRONTEND_URL"
echo
echo "Swagger:"
echo "  http://127.0.0.1:8000/docs"
echo


# Try to open browser.
if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$FRONTEND_URL" >/dev/null 2>&1 &
fi

ok "Startup completed successfully"