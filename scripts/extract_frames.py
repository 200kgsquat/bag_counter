from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


def extract_frames(
    video_path: Path,
    output_dir: Path,
    num_frames: int,
) -> None:
    capture = cv2.VideoCapture(str(video_path))

    if not capture.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = capture.get(cv2.CAP_PROP_FPS)

    if total_frames <= 0:
        raise RuntimeError("Could not determine frame count")

    output_dir.mkdir(parents=True, exist_ok=True)

    indices = np.linspace(
        0,
        total_frames - 1,
        num=min(num_frames, total_frames),
        dtype=int,
    )

    print(f"Total frames: {total_frames}")
    print(f"FPS: {fps:.2f}")
    print(f"Extracting {len(indices)} frames")

    saved = 0

    for i, frame_index in enumerate(indices):
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(frame_index))

        ok, frame = capture.read()

        if not ok:
            print(f"Failed to read frame {frame_index}")
            continue

        filename = (
            output_dir
            / f"frame_{i:04d}_source_{frame_index:06d}.jpg"
        )

        if cv2.imwrite(str(filename), frame):
            saved += 1

    capture.release()

    print(f"Saved {saved} frames to {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--video",
        type=Path,
        default=Path("data/input.mp4"),
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/dataset/raw_images"),
    )

    parser.add_argument(
        "--num-frames",
        type=int,
        default=200,
    )

    args = parser.parse_args()

    extract_frames(
        video_path=args.video,
        output_dir=args.output,
        num_frames=args.num_frames,
    )


if __name__ == "__main__":
    main()