from pathlib import Path

import pytest

from app.cv.pipeline import (
    _validate_decoded_frame_count,
    _validate_output_file,
)


def test_rejects_video_without_decodable_frames() -> None:
    with pytest.raises(
        RuntimeError,
        match="does not contain any decodable frames",
    ):
        _validate_decoded_frame_count(
            processed_frames=0,
            total_frames=0,
        )


def test_rejects_suspicious_early_decoder_stop() -> None:
    with pytest.raises(
        RuntimeError,
        match="processed 3 of 100 declared frames",
    ):
        _validate_decoded_frame_count(
            processed_frames=3,
            total_frames=100,
        )


def test_allows_small_frame_metadata_difference() -> None:
    _validate_decoded_frame_count(
        processed_frames=97,
        total_frames=100,
    )


def test_allows_unknown_frame_count_after_successful_decode() -> None:
    _validate_decoded_frame_count(
        processed_frames=3,
        total_frames=0,
    )


def test_rejects_missing_output_file(tmp_path: Path) -> None:
    with pytest.raises(
        RuntimeError,
        match="Output video was not created",
    ):
        _validate_output_file(tmp_path / "missing.mp4")


def test_rejects_empty_output_file(tmp_path: Path) -> None:
    output_path = tmp_path / "empty.mp4"
    output_path.touch()

    with pytest.raises(
        RuntimeError,
        match="Output video is empty",
    ):
        _validate_output_file(output_path)


def test_accepts_non_empty_output_file(tmp_path: Path) -> None:
    output_path = tmp_path / "output.mp4"
    output_path.write_bytes(b"video")

    _validate_output_file(output_path)
