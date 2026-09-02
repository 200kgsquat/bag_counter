from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
from tqdm import tqdm

from app.cv.detector import Detector
from app.cv.types import Detection


@dataclass(slots=True)
class ProcessingStats:
    frames_processed: int
    source_fps: float
    processing_fps: float
    width: int
    height: int
    detections_total: int
    detections_by_class: dict[str, int]


class VideoProcessor:
    def __init__(self, detector: Detector) -> None:
        self.detector = detector

    def process(
        self,
        input_path: str | Path,
        output_path: str | Path,
    ) -> ProcessingStats:
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FileNotFoundError(f"Video not found: {input_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        capture = cv2.VideoCapture(str(input_path))
        if not capture.isOpened():
            raise RuntimeError(f"Cannot open video: {input_path}")

        source_fps = float(capture.get(cv2.CAP_PROP_FPS))
        if source_fps <= 0:
            source_fps = 25.0

        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))

        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            source_fps,
            (width, height),
        )

        if not writer.isOpened():
            capture.release()
            raise RuntimeError(f"Cannot create output video: {output_path}")

        class_counts: Counter[str] = Counter()
        detections_total = 0
        frames_processed = 0
        started_at = time.perf_counter()

        try:
            with tqdm(
                total=total_frames or None,
                desc="MMDetection inference",
                unit="frame",
            ) as progress:
                while True:
                    ok, frame = capture.read()
                    if not ok:
                        break

                    detections = self.detector.predict(frame)

                    for detection in detections:
                        class_counts[detection.class_name] += 1
                        detections_total += 1
                        self._draw_detection(frame, detection)

                    frames_processed += 1
                    elapsed = time.perf_counter() - started_at
                    processing_fps = frames_processed / elapsed if elapsed else 0.0

                    self._draw_overlay(
                        frame=frame,
                        frame_detections=len(detections),
                        processing_fps=processing_fps,
                    )

                    writer.write(frame)
                    progress.update(1)

        finally:
            capture.release()
            writer.release()

        elapsed = time.perf_counter() - started_at
        processing_fps = frames_processed / elapsed if elapsed else 0.0

        stats = ProcessingStats(
            frames_processed=frames_processed,
            source_fps=source_fps,
            processing_fps=processing_fps,
            width=width,
            height=height,
            detections_total=detections_total,
            detections_by_class=dict(class_counts.most_common()),
        )

        self._write_stats(output_path.with_suffix(".json"), stats)
        return stats

    @staticmethod
    def _draw_detection(frame, detection: Detection) -> None:
        x1, y1, x2, y2 = detection.bbox_xyxy.astype(int)

        cv2.rectangle(
            frame,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2,
        )

        label = f"{detection.class_name} {detection.score:.2f}"

        cv2.putText(
            frame,
            label,
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )

    @staticmethod
    def _draw_overlay(
        frame,
        *,
        frame_detections: int,
        processing_fps: float,
    ) -> None:
        cv2.rectangle(frame, (12, 12), (350, 92), (0, 0, 0), -1)

        cv2.putText(
            frame,
            f"Detections/frame: {frame_detections}",
            (28, 43),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

        cv2.putText(
            frame,
            f"Processing FPS: {processing_fps:.1f}",
            (28, 75),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )

    @staticmethod
    def _write_stats(path: Path, stats: ProcessingStats) -> None:
        with path.open("w", encoding="utf-8") as file:
            json.dump(
                asdict(stats),
                file,
                ensure_ascii=False,
                indent=2,
            )
