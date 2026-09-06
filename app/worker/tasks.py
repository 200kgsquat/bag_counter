from __future__ import annotations

import os
from pathlib import Path

from app.cv.detector import MMDetectionDetector
from app.cv.pipeline import VideoProcessingPipeline
from app.cv.settings import DEFAULT_DETECTION_SCORE_THRESHOLD
from app.job_store import (
    write_job_result,
    write_job_status,
)
from app.worker.celery_app import celery_app


_detector: MMDetectionDetector | None = None


MODEL_CONFIG = Path(
    os.getenv(
        "MODEL_CONFIG",
        "configs/rtmdet_bag.py",
    )
)

MODEL_CHECKPOINT = Path(
    os.getenv(
        "MODEL_CHECKPOINT",
        "checkpoints/bag_detector.pth",
    )
)

DEVICE = os.getenv(
    "MODEL_DEVICE",
    "cuda:0",
)

SCORE_THRESHOLD = float(
    os.getenv(
        "SCORE_THRESHOLD",
        str(DEFAULT_DETECTION_SCORE_THRESHOLD),
    )
)


def get_detector() -> MMDetectionDetector:
    global _detector

    if _detector is None:
        print(
            f"Loading detector "
            f"config={MODEL_CONFIG} "
            f"checkpoint={MODEL_CHECKPOINT} "
            f"device={DEVICE}"
        )

        _detector = MMDetectionDetector(
            config_path=MODEL_CONFIG,
            checkpoint_path=MODEL_CHECKPOINT,
            device=DEVICE,
            score_threshold=SCORE_THRESHOLD,
        )

    return _detector


@celery_app.task(
    bind=True,
    name="process_video",
)
def process_video(
    self,
    input_path: str,
    output_path: str,
) -> dict:
    input_path_obj = Path(input_path)
    output_path_obj = Path(output_path)

    job_dir = output_path_obj.parent

    write_job_status(
        job_dir,
        {
            "status": "processing",
            "progress": 0.0,
            "processed_frames": 0,
            "total_frames": 0,
        },
    )

    last_saved_frame = 0

    try:
        detector = get_detector()

        pipeline = VideoProcessingPipeline(
            detector=detector,
        )

        def update_progress(
            processed_frames: int,
            total_frames: int,
        ) -> None:
            nonlocal last_saved_frame

            progress = (
                processed_frames
                / total_frames
                * 100.0
                if total_frames > 0
                else 0.0
            )

            progress = round(
                progress,
                2,
            )

            # Keep Celery metadata as well,
            # but the UI no longer depends on it.
            self.update_state(
                state="PROGRESS",
                meta={
                    "processed_frames": processed_frames,
                    "total_frames": total_frames,
                    "progress": progress,
                },
            )

            # Avoid writing to disk on every single frame.
            should_save = (
                processed_frames
                - last_saved_frame
                >= 10
                or (
                    total_frames > 0
                    and processed_frames >= total_frames
                )
            )

            if not should_save:
                return

            write_job_status(
                job_dir,
                {
                    "status": "processing",
                    "progress": progress,
                    "processed_frames": processed_frames,
                    "total_frames": total_frames,
                },
            )

            last_saved_frame = processed_frames

        result = pipeline.process(
            input_path=input_path_obj,
            output_path=output_path_obj,
            progress_callback=update_progress,
        )

        payload = {
            "total_bags": result.total_bags,
            "processed_frames": result.processed_frames,
            "total_frames": result.total_frames,
            "elapsed_seconds": round(
                result.elapsed_seconds,
                2,
            ),
            "output_path": str(
                result.output_path
            ),
            "anomalies": [
                {
                    "type": anomaly.type.value,
                    "frame_index": anomaly.frame_index,
                    "track_id": anomaly.track_id,
                    "message": anomaly.message,
                }
                for anomaly in result.anomalies
            ],
        }

        write_job_result(
            job_dir,
            payload,
        )

        write_job_status(
            job_dir,
            {
                "status": "completed",
                "progress": 100.0,
                **payload,
            },
        )

        return payload

    except Exception as exc:
        write_job_status(
            job_dir,
            {
                "status": "failed",
                "progress": 0.0,
                "error": str(exc),
            },
        )

        raise