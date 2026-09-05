import numpy as np

from app.cv.settings import (
    DEFAULT_DETECTION_SCORE_THRESHOLD,
    DEFAULT_TRACK_ACTIVATION_THRESHOLD,
)
from app.cv.tracker import ByteTracker
from app.cv.types import Detection


def make_detection(score: float) -> Detection:
    return Detection(
        bbox_xyxy=np.array(
            [10.0, 10.0, 30.0, 30.0],
            dtype=np.float32,
        ),
        score=score,
        class_id=0,
        class_name="bag",
    )


def test_detector_preserves_bytetrack_low_score_band() -> None:
    assert DEFAULT_DETECTION_SCORE_THRESHOLD <= 0.10
    assert (
        DEFAULT_DETECTION_SCORE_THRESHOLD
        < DEFAULT_TRACK_ACTIVATION_THRESHOLD
    )


def test_low_score_detection_keeps_existing_track() -> None:
    tracker = ByteTracker(
        frame_rate=30,
        track_activation_threshold=(
            DEFAULT_TRACK_ACTIVATION_THRESHOLD
        ),
    )

    initial_tracks = tracker.update(
        [make_detection(score=0.90)]
    )
    assert len(initial_tracks) == 1

    continued_tracks = tracker.update(
        [make_detection(score=0.15)]
    )

    assert len(continued_tracks) == 1
    assert (
        continued_tracks[0].track_id
        == initial_tracks[0].track_id
    )
