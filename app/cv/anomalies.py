from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import hypot

from app.cv.tracker import TrackedDetection


class AnomalyType(str, Enum):
    REVERSE_MOVEMENT = "reverse_movement"
    LOW_CONFIDENCE_NEAR_LINE = "low_confidence_near_line"


@dataclass(frozen=True, slots=True)
class AnomalyEvent:
    type: AnomalyType
    frame_index: int
    track_id: int
    message: str


class AnomalyMonitor:
    def __init__(
        self,
        line_start: tuple[float, float],
        line_end: tuple[float, float],
        *,
        expected_direction: int = -1,
        hysteresis_px: float = 20.0,
        near_line_px: float = 50.0,
        low_confidence_threshold: float = 0.40,
    ) -> None:
        self.line_start = line_start
        self.line_end = line_end
        self.expected_direction = expected_direction
        self.hysteresis_px = hysteresis_px
        self.near_line_px = near_line_px
        self.low_confidence_threshold = (
            low_confidence_threshold
        )

        self.last_side: dict[int, int] = {}

        self.reported_reverse: set[int] = set()
        self.reported_low_confidence: set[int] = set()

    def update(
        self,
        tracks: list[TrackedDetection],
        frame_index: int,
    ) -> list[AnomalyEvent]:
        events: list[AnomalyEvent] = []

        for track in tracks:
            distance = self._signed_distance(
                track.center
            )

            # Suspicious low confidence near counting line.
            if (
                abs(distance) <= self.near_line_px
                and track.score
                < self.low_confidence_threshold
                and track.track_id
                not in self.reported_low_confidence
            ):
                self.reported_low_confidence.add(
                    track.track_id
                )

                events.append(
                    AnomalyEvent(
                        type=(
                            AnomalyType
                            .LOW_CONFIDENCE_NEAR_LINE
                        ),
                        frame_index=frame_index,
                        track_id=track.track_id,
                        message=(
                            f"Low confidence "
                            f"{track.score:.2f} "
                            "near count line"
                        ),
                    )
                )

            current_side = self._stable_side(
                distance
            )

            if current_side == 0:
                continue

            previous_side = self.last_side.get(
                track.track_id
            )

            if previous_side is None:
                self.last_side[
                    track.track_id
                ] = current_side
                continue

            if previous_side == current_side:
                continue

            movement_direction = (
                1
                if (
                    previous_side == -1
                    and current_side == 1
                )
                else -1
            )

            self.last_side[
                track.track_id
            ] = current_side

            if (
                movement_direction
                != self.expected_direction
                and track.track_id
                not in self.reported_reverse
            ):
                self.reported_reverse.add(
                    track.track_id
                )

                events.append(
                    AnomalyEvent(
                        type=AnomalyType.REVERSE_MOVEMENT,
                        frame_index=frame_index,
                        track_id=track.track_id,
                        message=(
                            "Bag crossed count line "
                            "in reverse direction"
                        ),
                    )
                )

        return events

    def _stable_side(
        self,
        distance: float,
    ) -> int:
        if abs(distance) <= self.hysteresis_px:
            return 0

        return 1 if distance > 0 else -1

    def _signed_distance(
        self,
        point: tuple[float, float],
    ) -> float:
        x, y = point

        x1, y1 = self.line_start
        x2, y2 = self.line_end

        dx = x2 - x1
        dy = y2 - y1

        line_length = hypot(dx, dy)

        cross_product = (
            dx * (y - y1)
            - dy * (x - x1)
        )

        return cross_product / line_length