from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import supervision as sv

from app.cv.settings import DEFAULT_TRACK_ACTIVATION_THRESHOLD
from app.cv.types import Detection


@dataclass(frozen=True, slots=True)
class TrackedDetection:
    bbox_xyxy: np.ndarray
    score: float
    class_id: int
    class_name: str
    track_id: int

    @property
    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.bbox_xyxy

        return (
            float((x1 + x2) / 2.0),
            float((y1 + y2) / 2.0),
        )


class ByteTracker:
    def __init__(
        self,
        *,
        frame_rate: int = 30,
        track_activation_threshold: float = (
            DEFAULT_TRACK_ACTIVATION_THRESHOLD
        ),
        lost_track_buffer: int = 30,
        minimum_matching_threshold: float = 0.8,
    ) -> None:
        self.tracker = sv.ByteTrack(
            frame_rate=frame_rate,
            track_activation_threshold=track_activation_threshold,
            lost_track_buffer=lost_track_buffer,
            minimum_matching_threshold=minimum_matching_threshold,
        )

    def update(
        self,
        detections: list[Detection],
    ) -> list[TrackedDetection]:

        if not detections:
            sv_detections = sv.Detections.empty()
        else:
            xyxy = np.stack(
                [d.bbox_xyxy for d in detections],
            )

            confidence = np.asarray(
                [d.score for d in detections],
                dtype=np.float32,
            )

            class_id = np.asarray(
                [d.class_id for d in detections],
                dtype=np.int32,
            )

            sv_detections = sv.Detections(
                xyxy=xyxy,
                confidence=confidence,
                class_id=class_id,
            )

        tracked = self.tracker.update_with_detections(
            sv_detections,
        )

        results: list[TrackedDetection] = []

        if tracked.tracker_id is None:
            return results

        for (
            bbox,
            score,
            class_id,
            track_id,
        ) in zip(
            tracked.xyxy,
            tracked.confidence,
            tracked.class_id,
            tracked.tracker_id,
        ):
            results.append(
                TrackedDetection(
                    bbox_xyxy=bbox.astype(np.float32),
                    score=float(score),
                    class_id=int(class_id),
                    class_name="bag",
                    track_id=int(track_id),
                )
            )

        return results
