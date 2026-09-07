from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    UploadFile,
)
from fastapi.responses import FileResponse

from app.job_store import (
    read_job_result,
    read_job_status,
    write_job_status,
)
from app.worker.celery_app import celery_app


app = FastAPI(
    title="Bag Counter API",
    version="0.1.0",
)


JOBS_DIR = Path(
    "data/jobs"
)


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
    filename = (
        file.filename
        or ""
    )

    if (
        Path(filename)
        .suffix
        .lower()
        != ".mp4"
    ):
        raise HTTPException(
            status_code=400,
            detail="Only .mp4 files are supported",
        )

    job_id = uuid4().hex

    job_dir = (
        JOBS_DIR
        / job_id
    )

    job_dir.mkdir(
        parents=True,
        exist_ok=False,
    )

    input_path = (
        job_dir
        / "input.mp4"
    )

    output_path = (
        job_dir
        / "output.mp4"
    )

    try:
        with input_path.open(
            "wb"
        ) as destination:
            while chunk := file.file.read(
                1024 * 1024
            ):
                destination.write(
                    chunk
                )

    finally:
        file.file.close()

    write_job_status(
        job_dir,
        {
            "status": "queued",
            "progress": 0.0,
            "processed_frames": 0,
            "total_frames": 0,
        },
    )

    try:
        celery_app.send_task(
            "process_video",
            args=[
                str(input_path),
                str(output_path),
            ],
            task_id=job_id,
        )

    except Exception as exc:
        write_job_status(
            job_dir,
            {
                "status": "failed",
                "progress": 0.0,
                "error": (
                    "Could not enqueue processing task: "
                    f"{exc}"
                ),
            },
        )

        raise HTTPException(
            status_code=503,
            detail="Could not enqueue processing task",
        ) from exc

    return {
        "job_id": job_id,
        "status": "queued",
    }


@app.get(
    "/jobs/{job_id}"
)
def get_job(
    job_id: str,
) -> dict:
    job_dir = (
        JOBS_DIR
        / job_id
    )

    if not job_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    # result.json is committed before the final status update. A stale or
    # temporarily unreadable status file must not hide a completed result.
    result = read_job_result(
        job_dir
    )

    if result is not None:
        return {
            **result,
            "job_id": job_id,
            "status": "completed",
            "progress": 100.0,
        }

    status = read_job_status(job_dir)
    if status is not None:
        return {"job_id": job_id, **status}

    # Missing/unreadable metadata is not evidence of processing failure.
    # A retryable HTTP response keeps the frontend polling the running job.
    raise HTTPException(
        status_code=503,
        detail="Job status is temporarily unavailable; retry shortly",
        headers={"Retry-After": "1"},
    )


@app.get(
    "/jobs/{job_id}/result"
)
def download_result(
    job_id: str,
) -> FileResponse:
    job_dir = (
        JOBS_DIR
        / job_id
    )

    if not job_dir.exists():
        raise HTTPException(
            status_code=404,
            detail="Job not found",
        )

    result = read_job_result(
        job_dir
    )

    if result is None:
        raise HTTPException(
            status_code=409,
            detail="Result is not ready yet",
        )

    output_path = (
        job_dir
        / "output.mp4"
    )

    if not output_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Result file not found",
        )

    if output_path.stat().st_size <= 0:
        raise HTTPException(
            status_code=404,
            detail="Result file is empty",
        )

    return FileResponse(
        path=output_path,
        media_type="video/mp4",
        filename=f"{job_id}.mp4",
    )
