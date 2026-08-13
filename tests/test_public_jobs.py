from pathlib import Path

from fastapi.testclient import TestClient

import insidegov.api as api_module
from insidegov.api import app
from insidegov.public_jobs import PublicJobRepository

client = TestClient(app)


def test_public_job_repository_persists_status_events_and_checkpoint(tmp_path):
    path = tmp_path / "jobs.sqlite3"
    first = PublicJobRepository(path)
    job = first.create("conversation", {"mechanism_id": "M8"}, "deepseek-v4-flash")
    first.update(
        job["id"], status="running", stage_index=2, stage_label="政企协商",
        checkpoint={"world_id": "world-1", "quarter": 1},
    )
    event = first.event(
        job["id"], "progress", 2, "企业提出补充条件", "政府需要重新计算兑现安排。",
        actor="项目企业",
    )

    reopened = PublicJobRepository(path)
    restored = reopened.get(job["id"])
    assert restored["status"] == "running"
    assert restored["checkpoint"]["quarter"] == 1
    assert reopened.events(job["id"], event["sequence"] - 1)[0]["actor"] == "项目企业"


def test_public_job_api_is_async_durable_and_has_no_mode_switch(tmp_path, monkeypatch):
    repository = PublicJobRepository(Path(tmp_path) / "api-jobs.sqlite3")
    monkeypatch.setattr(api_module, "public_job_repository", repository)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    launched = []
    monkeypatch.setattr(api_module, "launch_public_job", lambda _repo, job_id: launched.append(job_id))

    response = client.post("/experience/jobs", json={
        "scene": "conversation",
        "config": {"mechanism_id": "M8", "event_text": "企业融资口径发生变化。"},
    })
    assert response.status_code == 202
    job = response.json()
    assert job["status"] == "queued"
    assert job["model_name"] == "deepseek-v4-flash"
    assert launched == [job["id"]]

    forbidden = client.post("/experience/jobs", json={
        "scene": "conversation",
        "config": {"mechanism_id": "M8", "policy_mode": "deterministic"},
    })
    assert forbidden.status_code == 422

    listed = client.get("/experience/jobs").json()
    assert listed[0]["id"] == job["id"]
    assert "result" not in listed[0]


def test_failed_public_job_can_retry_from_checkpoint(tmp_path, monkeypatch):
    repository = PublicJobRepository(Path(tmp_path) / "retry-jobs.sqlite3")
    monkeypatch.setattr(api_module, "public_job_repository", repository)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(api_module, "launch_public_job", lambda _repo, _job_id: None)
    parent = repository.create("coordination", {"process_mode": "hybrid"}, "deepseek-v4-flash")
    repository.update(
        parent["id"], status="failed", error="timeout",
        checkpoint={"world_id": "world-checkpoint", "quarter": 2},
    )

    response = client.post(f"/experience/jobs/{parent['id']}/retry")
    assert response.status_code == 202
    retried = response.json()
    assert retried["parent_job_id"] == parent["id"]
    assert retried["attempt"] == 2
    assert retried["checkpoint"]["quarter"] == 2
