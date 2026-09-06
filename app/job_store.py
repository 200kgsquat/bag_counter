from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


STATUS_FILENAME = "status.json"
RESULT_FILENAME = "result.json"


def _write_json_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary_path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    os.replace(
        temporary_path,
        path,
    )


def _read_json(
    path: Path,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8",
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None

    if not isinstance(
        payload,
        dict,
    ):
        return None

    return payload


def write_job_status(
    job_dir: Path,
    payload: dict[str, Any],
) -> None:
    _write_json_atomic(
        job_dir / STATUS_FILENAME,
        payload,
    )


def read_job_status(
    job_dir: Path,
) -> dict[str, Any] | None:
    return _read_json(
        job_dir / STATUS_FILENAME,
    )


def write_job_result(
    job_dir: Path,
    payload: dict[str, Any],
) -> None:
    _write_json_atomic(
        job_dir / RESULT_FILENAME,
        payload,
    )


def read_job_result(
    job_dir: Path,
) -> dict[str, Any] | None:
    return _read_json(
        job_dir / RESULT_FILENAME,
    )