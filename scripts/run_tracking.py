from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2
from tqdm import tqdm

from app.cv.counter import LineCrossingCounter
from app.cv.detector import MMDetectionDetector
from app.cv.tracker import ByteTracker


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=Path,
        default=Path("data/input.mp4"),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/counted.mp4"),
    )

    parser.add_argument(
        "--config",
        type=Path,
        default=Path("configs/rtmdet_bag.py"),
    )

    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path(
            "work_dirs/rtmdet_bag/"
            "best_coco_bbox_mAP_epoch_35.pth"
        ),
    )

    parser.add_argument(
        "--device",
        default="cuda:0",
    )

    parser.add_argument(
        "--score-threshold",
        type=float,
        default=0.25,
    )

    args = parser.parse_args()

    detector = MMDetectionDetector(
        config_path=args.config,
        checkpoint_path=args.checkpoint,
        device=args.device,
        score_threshold=args.score_threshold,
    )

    capture = cv2.VideoCapture(str(args.input))

    if not capture.isOpened():
        raise RuntimeError(
            f"Cannot open video: {args.input}"
        )

    fps = capture.get(cv2.CAP_PROP_FPS)

    if fps <= 0:
        fps = 25.0

    width = int(
        capture.get(cv2.CAP_PROP_FRAME_WIDTH)
    )

    height = int(
        capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
    )

    total_frames = int(
        capture.get(cv2.CAP_PROP_FRAME_COUNT)
    )

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    writer = cv2.VideoWriter(
        str(args.output),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )

    if not writer.isOpened():
        capture.release()
        raise RuntimeError(
            f"Cannot create output video: {args.output}"
        )

    tracker = ByteTracker(
        frame_rate=int(round(fps)),
        track_activation_threshold=0.25,
        lost_track_buffer=30,
        minimum_matching_threshold=0.8,
    )

    # Counting line
    line_start = (
        int(width * 0.32),
        int(height * 0.20),
    )

    line_end = (
        int(width * 0.58),
        int(height * 0.68),
    )

    counter = LineCrossingCounter(
        line_start=line_start,
        line_end=line_end,
        hysteresis_px=20,
        direction=-1,
    )

    started_at = time.perf_counter()
    processed_frames = 0

    try:
        with tqdm(
            total=total_frames,
            desc="Detection + tracking + counting",
            unit="frame",
        ) as progress:

            while True:
                ok, frame = capture.read()

                if not ok:
                    break

                # 1. Detection
                detections = detector.predict(frame)

                # 2. Tracking
                tracks = tracker.update(detections)

                # 3. Counting
                crossing_events = counter.update(tracks)

                for event in crossing_events:
                    print(
                        f"COUNTED track #{event.track_id} "
                        f"-> total={event.total_count}"
                    )

                # 4. Draw tracked bags
                for track in tracks:
                    x1, y1, x2, y2 = (
                        track.bbox_xyxy.astype(int)
                    )

                    cv2.rectangle(
                        frame,
                        (x1, y1),
                        (x2, y2),
                        (0, 255, 0),
                        2,
                    )

                    label = (
                        f"BAG #{track.track_id} "
                        f"{track.score:.2f}"
                    )

                    cv2.putText(
                        frame,
                        label,
                        (x1, max(20, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.50,
                        (0, 255, 0),
                        1,
                        cv2.LINE_AA,
                    )

                    cx, cy = track.center

                    cv2.circle(
                        frame,
                        (int(cx), int(cy)),
                        3,
                        (0, 0, 255),
                        -1,
                    )

                # 5. Draw counting line
                cv2.line(
                    frame,
                    line_start,
                    line_end,
                    (0, 255, 255),
                    2,
                    cv2.LINE_AA,
                )

                cv2.putText(
                    frame,
                    "COUNT LINE",
                    (
                        line_start[0],
                        max(20, line_start[1] - 8),
                    ),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.40,
                    (0, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

                processed_frames += 1

                elapsed = (
                    time.perf_counter()
                    - started_at
                )

                processing_fps = (
                    processed_frames / elapsed
                    if elapsed > 0
                    else 0.0
                )

                # 6. Compact overlay
                cv2.rectangle(
                    frame,
                    (12, 12),
                    (205, 80),
                    (0, 0, 0),
                    -1,
                )

                cv2.putText(
                    frame,
                    f"TOTAL: {counter.total_count}",
                    (20, 33),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

                cv2.putText(
                    frame,
                    f"Tracks: {len(tracks)}",
                    (20, 54),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.38,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

                cv2.putText(
                    frame,
                    f"FPS: {processing_fps:.1f}",
                    (20, 73),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.38,
                    (255, 255, 255),
                    1,
                    cv2.LINE_AA,
                )

                writer.write(frame)
                progress.update(1)

    finally:
        capture.release()
        writer.release()

    print()
    print("Processing completed.")
    print(f"Total bags counted: {counter.total_count}")
    print(f"Video: {args.output}")


if __name__ == "__main__":
    main()