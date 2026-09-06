"""Load the configured detector and run one frame inside the GPU worker image."""

from __future__ import annotations

import sys


def main() -> None:
    # Keep GPU dependencies out of imports used by the core test environment.
    import cv2
    import mmcv
    import mmdet
    import numpy as np
    import torch

    from app.worker.tasks import (
        DEVICE,
        MODEL_CHECKPOINT,
        MODEL_CONFIG,
        get_detector,
    )

    for path in (MODEL_CONFIG, MODEL_CHECKPOINT):
        if not path.is_file():
            raise FileNotFoundError(f"Required model file is missing: {path}")

    device = torch.device(DEVICE)
    if device.type != "cuda" or not torch.cuda.is_available():
        raise RuntimeError(
            f"CUDA is required for the worker startup check; configured device: {DEVICE}"
        )

    print("Python:", sys.version.split()[0])
    print("OpenCV:", cv2.__version__)
    print("MMCV:", mmcv.__version__)
    print("MMDetection:", mmdet.__version__)
    print("GPU:", torch.cuda.get_device_name(device))
    print("Config:", MODEL_CONFIG)
    print("Checkpoint:", MODEL_CHECKPOINT)

    detector = get_detector()
    detections = detector.predict(np.zeros((640, 640, 3), dtype=np.uint8))
    # Surface asynchronous CUDA errors before reporting success.
    torch.cuda.synchronize(device)
    print(f"MODEL_OK: checkpoint loaded; GPU inference completed ({len(detections)} detections)")


if __name__ == "__main__":
    main()
