from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from math import ceil
from pathlib import Path

import cv2

from app.cv.anomalies import AnomalyEvent, AnomalyMonitor
from app.cv.counter import LineCrossingCounter
from app.cv.settings import DEFAULT_TRACK_ACTIVATION_THRESHOLD
from app.cv.tracker import ByteTracker
from app.cv.types import Detector

ProgressCallback = Callable[[int, int], None]

FRAME_COUNT_TOLERANCE_RATIO = 0.01
MIN_FRAME_COUNT_TOLERANCE = 5


@dataclass(frozen=True, slots=True)
class ProcessingResult:
    anomalies: tuple[AnomalyEvent, ...]
    total_bags: int
    processed_frames: int
    total_frames: int
    elapsed_seconds: float
    output_path: Path


def _validate_decoded_frame_count(
    processed_frames: int,
    total_frames: int,
) -> None:
    """Reject empty videos and suspicious early decoder termination.

    OpenCV frame-count metadata can be slightly inaccurate, so a small
    absolute/relative shortfall is accepted instead of requiring equality.
    """
    if processed_frames <= 0:
        raise RuntimeError(
            "Video does not contain any decodable frames"
        )

    if total_frames <= 0:
        return

    allowed_shortfall = max(
        MIN_FRAME_COUNT_TOLERANCE,
        ceil(total_frames * FRAME_COUNT_TOLERANCE_RATIO),
    )
    missing_frames = total_frames - processed_frames

    if missing_frames > allowed_shortfall:
        raise RuntimeError(
            "Video decoding stopped unexpectedly: "
            f"processed {processed_frames} of "
            f"{total_frames} declared frames"
        )


def _validate_output_file(output_path: Path) -> None:
    """Ensure the video writer produced a non-empty result file."""
    if not output_path.is_file():
        raise RuntimeError(
            f"Output video was not created: {output_path}"
        )

    try:
        output_size = output_path.stat().st_size
    except OSError as exc:
        raise RuntimeError(
            f"Cannot inspect output video: {output_path}"
        ) from exc

    if output_size <= 0:
        raise RuntimeError(
            f"Output video is empty: {output_path}"
        )


class VideoProcessingPipeline:
    def __init__(
        self,
        detector: Detector,
    ) -> None:
        self.detector = detector

    def process(
        self,
        input_path: Path,
        output_path: Path,
        progress_callback: ProgressCallback | None = None,
    ) -> ProcessingResult:
        capture = cv2.VideoCapture(str(input_path))

        if not capture.isOpened():
            raise RuntimeError(
                f"Cannot open video: {input_path}"
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

        if width <= 0 or height <= 0:
            capture.release()

            raise RuntimeError(
                "Video has invalid frame dimensions: "
                f"{width}x{height}"
            )

        total_frames = int(
            capture.get(cv2.CAP_PROP_FRAME_COUNT)
        )

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (width, height),
        )

        if not writer.isOpened():
            capture.release()

            raise RuntimeError(
                f"Cannot create video: {output_path}"
            )

        tracker = ByteTracker(
            frame_rate=round(fps),
            track_activation_threshold=(
                DEFAULT_TRACK_ACTIVATION_THRESHOLD
            ),
            lost_track_buffer=30,
            minimum_matching_threshold=0.8,
        )

        # Verified counting line.
        line_start = (
            int(width * 0.27),
            int(height * 0.32),
        )

        line_end = (
            int(width * 0.50),
            int(height * 0.67),
        )

        counter = LineCrossingCounter(
            line_start=line_start,
            line_end=line_end,
            hysteresis_px=20,
            direction=-1,
        )

        anomaly_monitor = AnomalyMonitor(
            line_start=line_start,
            line_end=line_end,
            expected_direction=-1,
            hysteresis_px=20,
            near_line_px=50,
            low_confidence_threshold=0.40,
        )

        all_anomalies: list[AnomalyEvent] = []

        started_at = time.perf_counter()
        processed_frames = 0

        try:
            while True:
                ok, frame = capture.read()

                if not ok:
                    break

                # 1. Detection
                detections = self.detector.predict(
                    frame
                )

                # 2. Tracking
                tracks = tracker.update(
                    detections
                )

                # 3. Counting
                crossing_events = counter.update(
                    tracks
                )

                for event in crossing_events:
                    print(
                        f"COUNTED track #{event.track_id} "
                        f"-> total={event.total_count}"
                    )

                # 4. Anomaly monitoring
                anomalies = anomaly_monitor.update(
                    tracks=tracks,
                    frame_index=processed_frames,
                )

                all_anomalies.extend(
                    anomalies
                )

                for anomaly in anomalies:
                    print(
                        f"ANOMALY "
                        f"{anomaly.type.value} "
                        f"track=#{anomaly.track_id} "
                        f"frame={anomaly.frame_index}"
                    )

                # 5. Draw tracked bags
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

                    cv2.putText(
                        frame,
                        (
                            f"BAG #{track.track_id} "
                            f"{track.score:.2f}"
                        ),
                        (
                            x1,
                            max(20, y1 - 8),
                        ),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.50,
                        (0, 255, 0),
                        1,
                        cv2.LINE_AA,
                    )

                    cx, cy = track.center

                    cv2.circle(
                        frame,
                        (
                            int(cx),
                            int(cy),
                        ),
                        3,
                        (0, 0, 255),
                        -1,
                    )

                # 6. Draw counting line
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
                        max(
                            20,
                            line_start[1] - 8,
                        ),
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

                # 7. Compact overlay
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

                if progress_callback is not None:
                    progress_callback(
                        processed_frames,
                        total_frames,
                    )

        finally:
            capture.release()
            writer.release()

        _validate_decoded_frame_count(
            processed_frames=processed_frames,
            total_frames=total_frames,
        )
        _validate_output_file(output_path)

        elapsed_seconds = (
            time.perf_counter()
            - started_at
        )

        return ProcessingResult(
            anomalies=tuple(all_anomalies),
            total_bags=counter.total_count,
            processed_frames=processed_frames,
            total_frames=total_frames,
            elapsed_seconds=elapsed_seconds,
            output_path=output_path,
        )
