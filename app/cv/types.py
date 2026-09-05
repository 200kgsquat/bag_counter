from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np


@dataclass(frozen=True, slots=True)
class Detection:
    """Framework-agnostic object detection result."""

    bbox_xyxy: np.ndarray
    score: float
    class_id: int
    class_name: str

    @property
    def x1(self) -> float:
        return float(self.bbox_xyxy[0])

    @property
    def y1(self) -> float:
        return float(self.bbox_xyxy[1])

    @property
    def x2(self) -> float:
        return float(self.bbox_xyxy[2])

    @property
    def y2(self) -> float:
        return float(self.bbox_xyxy[3])

    @property
    def center(self) -> tuple[float, float]:
        return (
            (self.x1 + self.x2) / 2.0,
            (self.y1 + self.y2) / 2.0,
        )


class Detector(Protocol):
    """Framework-independent detector interface used by pipelines."""

    def predict(self, frame: np.ndarray) -> list[Detection]:
        ...
