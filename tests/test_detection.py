import numpy as np

from app.cv.types import Detection


def test_detection_center() -> None:
    detection = Detection(
        bbox_xyxy=np.array([10, 20, 30, 60], dtype=np.float32),
        score=0.9,
        class_id=0,
        class_name="bag",
    )

    assert detection.center == (20.0, 40.0)
