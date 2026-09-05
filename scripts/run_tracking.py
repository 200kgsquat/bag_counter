from pathlib import Path

from app.cv.detector import MMDetectionDetector
from app.cv.pipeline import VideoProcessingPipeline
from app.cv.settings import DEFAULT_DETECTION_SCORE_THRESHOLD


def main() -> None:
    detector = MMDetectionDetector(
        config_path=Path(
            "configs/rtmdet_bag.py"
        ),
        checkpoint_path=Path(
            "work_dirs/rtmdet_bag/"
            "best_coco_bbox_mAP_epoch_35.pth"
        ),
        device="cuda:0",
        score_threshold=DEFAULT_DETECTION_SCORE_THRESHOLD,
    )

    pipeline = VideoProcessingPipeline(
        detector=detector
    )

    result = pipeline.process(
        input_path=Path("data/input.mp4"),
        output_path=Path(
            "outputs/counted.mp4"
        ),
    )

    print()
    print("Processing completed.")
    print(f"Total bags: {result.total_bags}")
    print(
        f"Frames: "
        f"{result.processed_frames}/"
        f"{result.total_frames}"
    )
    print(
        f"Time: {result.elapsed_seconds:.1f}s"
    )
    print(f"Video: {result.output_path}")


if __name__ == "__main__":
    main()
