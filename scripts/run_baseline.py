from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.cv.detector import MMDetectionDetector
from app.cv.video_processor import VideoProcessor


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run MMDetection baseline on a video."
    )

    parser.add_argument("--input", type=Path, default=Path("data/input.mp4"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/baseline.mp4"),
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--score-threshold", type=float, default=0.25)

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    detector = MMDetectionDetector(
        config_path=args.config,
        checkpoint_path=args.checkpoint,
        device=args.device,
        score_threshold=args.score_threshold,
    )

    processor = VideoProcessor(detector)
    stats = processor.process(
        input_path=args.input,
        output_path=args.output,
    )

    print("\nBaseline completed.")
    print(f"Video: {args.output}")
    print(f"Stats: {args.output.with_suffix('.json')}")
    print(json.dumps(stats.detections_by_class, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
