from __future__ import annotations

from pathlib import Path

import numpy as np
from mmdet.apis import inference_detector, init_detector

from app.cv.settings import DEFAULT_DETECTION_SCORE_THRESHOLD
from app.cv.types import Detection, Detector

__all__ = ["Detector", "MMDetectionDetector"]


class MMDetectionDetector:
    """Thin adapter around MMDetection.

    The rest of the application should depend on Detector/Detection,
    not on MMDetection-specific result objects.
    """

    def __init__(
        self,
        config_path: str | Path,
        checkpoint_path: str | Path,
        *,
        device: str = "cuda:0",
        score_threshold: float = DEFAULT_DETECTION_SCORE_THRESHOLD,
    ) -> None:
        if not 0.0 <= score_threshold <= 1.0:
            raise ValueError("score_threshold must be in [0, 1]")

        self.score_threshold = score_threshold

        self.model = init_detector(
            config=str(config_path),
            checkpoint=str(checkpoint_path),
            device=device,
        )

        dataset_meta = getattr(self.model, "dataset_meta", None) or {}
        classes = dataset_meta.get("classes")

        if not classes:
            raise RuntimeError(
                "MMDetection model does not expose dataset_meta['classes']; "
                "cannot map class ids to readable names."
            )

        self.class_names: tuple[str, ...] = tuple(classes)

    def predict(self, frame: np.ndarray) -> list[Detection]:
        result = inference_detector(self.model, frame)
        instances = result.pred_instances.cpu()

        bboxes = instances.bboxes.numpy()
        scores = instances.scores.numpy()
        labels = instances.labels.numpy()

        detections: list[Detection] = []

        for bbox, score, class_id in zip(bboxes, scores, labels):
            score_value = float(score)

            if score_value < self.score_threshold:
                continue

            class_id_value = int(class_id)

            detections.append(
                Detection(
                    bbox_xyxy=np.asarray(bbox, dtype=np.float32),
                    score=score_value,
                    class_id=class_id_value,
                    class_name=self.class_names[class_id_value],
                )
            )

        return detections
