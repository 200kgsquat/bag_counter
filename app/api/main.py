from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from celery.result import AsyncResult
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.worker.celery_app import celery_app


app = FastAPI(
    title="Bag Counter API",
    version="0.1.0",
)

JOBS_DIR = Path("data/jobs")


@app.on_event("startup")
def startup() -> None:
    JOBS_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
    }


@app.post(
    "/jobs",
    status_code=202,
)
def create_job(
    file: UploadFile = File(...),
) -> dict:
    filename = file.filename or ""

    if Path(filename).suffix.lower() != ".mp4":
        raise HTTPException(
            status_code=400,
            detail="Only .mp4 files are supported",
        )

    job_id = uuid4().hex

    job_dir = JOBS_DIR / job_id

    job_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    input_path = job_dir / "input.mp4"
    output_path = job_dir / "output.mp4"

    try:
        with input_path.open("wb") as destination:
            while chunk := file.file.read(
                1024 * 1024
            ):
                destination.write(chunk)

    finally:
        file.file.close()

    celery_app.send_task(
        "process_video",
        args=[
            str(input_path),
            str(output_path),
        ],
        task_id=job_id,
    )

    return {
        "job_id": job_id,
        "status": "queued",
    }


@app.get("/jobs/{job_id}")
def get_job(
    job_id: str,
) -> dict:
    job_dir = JOBS_DIR / job_id

    if not job_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    task = AsyncResult(
        job_id,
        app=celery_app,
    )

    if task.state == "PENDING":
        return {
            "job_id": job_id,
            "status": "queued",
            "progress": 0.0,
        }

    if task.state in {
        "STARTED",
        "PROGRESS",
    }:
        info = (
            task.info
            if isinstance(
                task.info,
                dict,
            )
            else {}
        )

        return {
            "job_id": job_id,
            "status": "processing",
            "progress": info.get(
                "progress",
                0.0,
            ),
            "processed_frames": info.get(
                "processed_frames",
                0,
            ),
            "total_frames": info.get(
                "total_frames",
                0,
            ),
        }

    if task.state == "SUCCESS":
        result = (
            task.result
            if isinstance(
                task.result,
                dict,
            )
            else {}
        )

        return {
            "job_id": job_id,
            "status": "completed",
            "progress": 100.0,
            **result,
        }

    if task.state == "FAILURE":
        return {
            "job_id": job_id,
            "status": "failed",
            "error": str(task.info),
        }

    return {
        "job_id": job_id,
        "status": task.state.lower(),
    }


@app.get("/jobs/{job_id}/result")
def download_result(
    job_id: str,
) -> FileResponse:
    job_dir = JOBS_DIR / job_id

    if not job_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    task = AsyncResult(
        job_id,
        app=celery_app,
    )

    if task.state != "SUCCESS":
        raise HTTPException(
            status_code=409,
            detail="Result is not ready yet",
        )

    output_path = (
        job_dir
        / "output.mp4"
    )

    if not output_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Result file not found",
        )

    return FileResponse(
        path=output_path,
        media_type="video/mp4",
        filename=f"{job_id}.mp4",
    )