import numpy as np

from app.cv.counter import LineCrossingCounter
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


def make_counter() -> LineCrossingCounter:
    """
    Horizontal counting line.

    For this line:
        y > 0 -> side +1
        y < 0 -> side -1

    direction=-1 therefore means:
        +1 -> -1 is the valid counting direction.
    """
    return LineCrossingCounter(
        line_start=(0.0, 0.0),
        line_end=(100.0, 0.0),
        hysteresis_px=5.0,
        direction=-1,
    )


def test_counts_expected_direction_crossing() -> None:
    counter = make_counter()

    # First observation establishes the initial side.
    events = counter.update(
        [make_track(track_id=1, x=50, y=20)]
    )

    assert events == []
    assert counter.total_count == 0

    # Same track crosses from +1 to -1.
    events = counter.update(
        [make_track(track_id=1, x=50, y=-20)]
    )

    assert len(events) == 1
    assert events[0].track_id == 1
    assert events[0].total_count == 1
    assert counter.total_count == 1


def test_does_not_count_reverse_direction() -> None:
    counter = make_counter()

    # Start on side -1.
    counter.update(
        [make_track(track_id=1, x=50, y=-20)]
    )

    # Move -1 -> +1.
    # This is opposite to configured direction=-1.
    events = counter.update(
        [make_track(track_id=1, x=50, y=20)]
    )

    assert events == []
    assert counter.total_count == 0


def test_same_track_cannot_be_counted_twice() -> None:
    counter = make_counter()

    # First valid crossing: +1 -> -1.
    counter.update(
        [make_track(track_id=42, x=50, y=20)]
    )

    events = counter.update(
        [make_track(track_id=42, x=50, y=-20)]
    )

    assert len(events) == 1
    assert counter.total_count == 1

    # Move back to the original side.
    counter.update(
        [make_track(track_id=42, x=50, y=20)]
    )

    # Cross in the valid direction again.
    # It must NOT increment because track 42 was already counted.
    events = counter.update(
        [make_track(track_id=42, x=50, y=-20)]
    )

    assert events == []
    assert counter.total_count == 1
    assert 42 in counter.counted_track_ids


def test_hysteresis_prevents_jitter_from_creating_crossing() -> None:
    counter = make_counter()

    # Establish stable +1 side.
    counter.update(
        [make_track(track_id=7, x=50, y=20)]
    )

    # These positions are inside the ±5 px dead zone.
    events = counter.update(
        [make_track(track_id=7, x=50, y=3)]
    )

    assert events == []
    assert counter.total_count == 0

    events = counter.update(
        [make_track(track_id=7, x=50, y=-3)]
    )

    assert events == []
    assert counter.total_count == 0

    # Only after leaving the dead zone on the other side
    # should a real crossing be registered.
    events = counter.update(
        [make_track(track_id=7, x=50, y=-20)]
    )

    assert len(events) == 1
    assert counter.total_count == 1


def test_different_tracks_are_counted_independently() -> None:
    counter = make_counter()

    counter.update(
        [
            make_track(track_id=1, x=30, y=20),
            make_track(track_id=2, x=70, y=20),
        ]
    )

    events = counter.update(
        [
            make_track(track_id=1, x=30, y=-20),
            make_track(track_id=2, x=70, y=-20),
        ]
    )

    assert len(events) == 2
    assert counter.total_count == 2
    assert counter.counted_track_ids == {1, 2}