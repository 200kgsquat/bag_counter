FROM pytorch/pytorch:2.1.2-cuda11.8-cudnn8-runtime

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip

# MMCV needs a wheel matching CUDA 11.8 + PyTorch 2.1
RUN pip install \
    mmcv==2.1.0 \
    -f https://download.openmmlab.com/mmcv/dist/cu118/torch2.1.0/index.html

RUN pip install \
    "numpy==1.26.4" \
    "opencv-python-headless==4.10.0.84" \
    "mmengine>=0.7.1,<1.0.0" \
    "mmdet==3.3.0" \
    "supervision==0.26.1" \
    "fastapi" \
    "uvicorn[standard]" \
    "celery" \
    "redis" \
    "python-multipart" \
    "tqdm>=4.66,<5"

COPY app ./app
COPY configs ./configs
COPY scripts ./scripts

RUN mkdir -p \
    /app/data/jobs \
    /app/checkpoints

CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]