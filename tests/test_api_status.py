from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import main
from app.job_store import write_job_result, write_job_status

JOB_ID = "a" * 32


@pytest.fixture
def job_client(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "JOBS_DIR", tmp_path)
    job_dir = tmp_path / JOB_ID
    job_dir.mkdir()
    with TestClient(main.app) as client:
        yield job_dir, client


@pytest.mark.parametrize("stale_status", ["processing", "failed"])
def test_completed_result_takes_precedence_over_stale_status(job_client, stale_status):
    job_dir, client = job_client
    write_job_status(job_dir, {"status": stale_status, "progress": 35})
    write_job_result(job_dir, {"total_bags": 127})
    response = client.get(f"/jobs/{JOB_ID}")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["progress"] == 100
    assert response.json()["total_bags"] == 127


def test_temporary_status_read_error_is_retryable(job_client, monkeypatch):
    job_dir, client = job_client
    write_job_status(job_dir, {"status": "processing", "progress": 35})
    original_read = Path.read_text

    def interrupted_read(path, *args, **kwargs):
        if path == job_dir / "status.json":
            raise PermissionError("temporary file access failure")
        return original_read(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", interrupted_read)
        response = client.get(f"/jobs/{JOB_ID}")
        assert response.status_code == 503
        assert response.headers["retry-after"] == "1"
    response = client.get(f"/jobs/{JOB_ID}")
    assert response.status_code == 200
    assert response.json()["status"] == "processing"


def test_missing_metadata_can_recover_to_completed(job_client):
    job_dir, client = job_client
    assert client.get(f"/jobs/{JOB_ID}").status_code == 503
    write_job_result(job_dir, {"total_bags": 127})
    assert client.get(f"/jobs/{JOB_ID}").json()["status"] == "completed"


def test_real_processing_failure_remains_terminal(job_client):
    job_dir, client = job_client
    write_job_status(job_dir, {"status": "failed", "error": "decoder failed"})
    response = client.get(f"/jobs/{JOB_ID}")
    assert response.status_code == 200
    assert response.json()["status"] == "failed"


def test_unknown_job_remains_not_found(job_client):
    _, client = job_client
    assert client.get('/jobs/' + 'b' * 32).status_code == 404


def test_result_download_does_not_depend_on_stale_status(job_client):
    job_dir, client = job_client
    write_job_status(job_dir, {"status": "processing"})
    write_job_result(job_dir, {"total_bags": 127})
    (job_dir / "output.mp4").write_bytes(b"test output")
    response = client.get(f"/jobs/{JOB_ID}/result")
    assert response.status_code == 200
    assert response.content == b"test output"
