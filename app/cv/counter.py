from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from app.cv.tracker import TrackedDetection


@dataclass(frozen=True, slots=True)
class CrossingEvent:
    track_id: int
    total_count: int


class LineCrossingCounter:
    """
    Counts tracked objects crossing an arbitrary 2D line.

    A small dead zone around the line is used as hysteresis,
    so bbox jitter near the line does not generate false crossings.
    """

    def __init__(
        self,
        line_start: tuple[float, float],
        line_end: tuple[float, float],
        *,
        hysteresis_px: float = 20.0,
        direction: int = 0,
    ) -> None:
        """
        direction:
            0  -> count crossings in both directions
            1  -> count -1 -> +1
            -1 -> count +1 -> -1
        """

        if line_start == line_end:
            raise ValueError("Counting line must have non-zero length")

        if direction not in (-1, 0, 1):
            raise ValueError("direction must be -1, 0 or 1")

        self.line_start = line_start
        self.line_end = line_end
        self.hysteresis_px = hysteresis_px
        self.direction = direction

        self.total_count = 0

        self.counted_track_ids: set[int] = set()

        # Последняя стабильная сторона линии для каждого track_id.
        #
        # -1 = одна сторона
        # +1 = другая сторона
        self.last_side: dict[int, int] = {}

    def update(
        self,
        tracks: list[TrackedDetection],
    ) -> list[CrossingEvent]:

        events: list[CrossingEvent] = []

        for track in tracks:
            point = track.center

            current_side = self._stable_side(point)

            # Объект находится прямо возле линии.
            # Ничего не меняем — ждём, когда он уверенно
            # окажется на одной из сторон.
            if current_side == 0:
                continue

            previous_side = self.last_side.get(
                track.track_id
            )

            # Первый раз увидели этот track.
            if previous_side is None:
                self.last_side[track.track_id] = (
                    current_side
                )
                continue

            # Сторона не изменилась.
            if previous_side == current_side:
                continue

            crossed = self._direction_matches(
                previous_side,
                current_side,
            )

            # В любом случае запоминаем новое
            # стабильное положение.
            self.last_side[track.track_id] = (
                current_side
            )

            if not crossed:
                continue

            if track.track_id in self.counted_track_ids:
                continue

            self.counted_track_ids.add(
                track.track_id
            )

            self.total_count += 1

            events.append(
                CrossingEvent(
                    track_id=track.track_id,
                    total_count=self.total_count,
                )
            )

        return events

    def _direction_matches(
        self,
        previous_side: int,
        current_side: int,
    ) -> bool:

        if self.direction == 0:
            return True

        if self.direction == 1:
            return (
                previous_side == -1
                and current_side == 1
            )

        return (
            previous_side == 1
            and current_side == -1
        )

    def _stable_side(
        self,
        point: tuple[float, float],
    ) -> int:
        distance = self._signed_distance_to_line(
            point
        )

        if abs(distance) <= self.hysteresis_px:
            return 0

        return 1 if distance > 0 else -1

    def _signed_distance_to_line(
        self,
        point: tuple[float, float],
    ) -> float:
        """
        Signed perpendicular distance from point to infinite line.

        Sign tells us which side of the line the point is on.
        """

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