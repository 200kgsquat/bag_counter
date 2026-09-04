from __future__ import annotations

import os
from pathlib import Path

from app.cv.detector import MMDetectionDetector
from app.cv.pipeline import VideoProcessingPipeline
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
        "0.25",
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
    detector = get_detector()

    pipeline = VideoProcessingPipeline(
        detector=detector,
    )

    def update_progress(
        processed_frames: int,
        total_frames: int,
    ) -> None:
        progress = (
            processed_frames
            / total_frames
            * 100.0
            if total_frames > 0
            else 0.0
        )

        self.update_state(
            state="PROGRESS",
            meta={
                "processed_frames": processed_frames,
                "total_frames": total_frames,
                "progress": round(progress, 2),
            },
        )

    result = pipeline.process(
        input_path=Path(input_path),
        output_path=Path(output_path),
        progress_callback=update_progress,
    )

    return {
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