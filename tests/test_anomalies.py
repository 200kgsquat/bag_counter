import numpy as np

from app.cv.anomalies import AnomalyMonitor, AnomalyType
from app.cv.tracker import TrackedDetection


def make_track(
    track_id: int,
    x: float,
    y: float,
    score: float = 0.9,
) -> TrackedDetection:
    """Create a synthetic tracked bag centered at (x, y)."""
    half_size = 5.0

    return TrackedDetection(
        bbox_xyxy=np.array(
            [
                x - half_size,
                y - half_size,
                x + half_size,
                y + half_size,
            ],
            dtype=np.float32,
        ),
        score=score,
        class_id=0,
        class_name="bag",
        track_id=track_id,
    )


def make_monitor() -> AnomalyMonitor:
    return AnomalyMonitor(
        line_start=(0.0, 0.0),
        line_end=(100.0, 0.0),
        expected_direction=-1,
        hysteresis_px=5.0,
        near_line_px=50.0,
        low_confidence_threshold=0.40,
    )


def test_reverse_movement_is_reported() -> None:
    monitor = make_monitor()

    # Establish side -1.
    monitor.update(
        [make_track(track_id=10, x=50, y=-20)],
        frame_index=1,
    )

    # -1 -> +1 means movement_direction=+1,
    # while expected_direction=-1.
    events = monitor.update(
        [make_track(track_id=10, x=50, y=20)],
        frame_index=2,
    )

    assert len(events) == 1

    event = events[0]

    assert event.type == AnomalyType.REVERSE_MOVEMENT
    assert event.track_id == 10
    assert event.frame_index == 2


def test_expected_direction_is_not_reported_as_reverse() -> None:
    monitor = make_monitor()

    # Establish side +1.
    monitor.update(
        [make_track(track_id=10, x=50, y=20)],
        frame_index=1,
    )

    # +1 -> -1 matches expected_direction=-1.
    events = monitor.update(
        [make_track(track_id=10, x=50, y=-20)],
        frame_index=2,
    )

    assert events == []


def test_reverse_movement_is_reported_only_once_per_track() -> None:
    monitor = make_monitor()

    # First reverse crossing.
    monitor.update(
        [make_track(track_id=10, x=50, y=-20)],
        frame_index=1,
    )

    events = monitor.update(
        [make_track(track_id=10, x=50, y=20)],
        frame_index=2,
    )

    assert len(events) == 1

    # Move back in expected direction.
    monitor.update(
        [make_track(track_id=10, x=50, y=-20)],
        frame_index=3,
    )

    # Reverse again.
    events = monitor.update(
        [make_track(track_id=10, x=50, y=20)],
        frame_index=4,
    )

    assert events == []


def test_low_confidence_near_line_is_reported() -> None:
    monitor = make_monitor()

    events = monitor.update(
        [
            make_track(
                track_id=20,
                x=50,
                y=20,
                score=0.25,
            )
        ],
        frame_index=100,
    )

    assert len(events) == 1

    event = events[0]

    assert (
        event.type
        == AnomalyType.LOW_CONFIDENCE_NEAR_LINE
    )
    assert event.track_id == 20
    assert event.frame_index == 100


def test_low_confidence_is_reported_only_once_per_track() -> None:
    monitor = make_monitor()

    first_events = monitor.update(
        [
            make_track(
                track_id=20,
                x=50,
                y=20,
                score=0.20,
            )
        ],
        frame_index=100,
    )

    second_events = monitor.update(
        [
            make_track(
                track_id=20,
                x=50,
                y=25,
                score=0.20,
            )
        ],
        frame_index=101,
    )

    assert len(first_events) == 1
    assert second_events == []


def test_low_confidence_far_from_line_is_not_reported() -> None:
    monitor = make_monitor()

    events = monitor.update(
        [
            make_track(
                track_id=30,
                x=50,
                y=100,
                score=0.20,
            )
        ],
        frame_index=100,
    )

    assert events == []


def test_high_confidence_near_line_is_not_reported() -> None:
    monitor = make_monitor()

    events = monitor.update(
        [
            make_track(
                track_id=30,
                x=50,
                y=20,
                score=0.90,
            )
        ],
        frame_index=100,
    )

    assert events == []