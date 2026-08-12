from fastapi.testclient import TestClient

from insidegov.api import app, repository, worlds
from insidegov.repository import WorldRepository

client = TestClient(app)


def test_create_step_branch_trace_export_and_restore(tmp_path):
    worlds.clear()
    original_root = repository.root
    repository.root = tmp_path
    created = client.post("/worlds", json={"seed": 11}).json()
    world_id = created["id"]
    stepped = client.post(f"/worlds/{world_id}/step", json={"quarters": 4}).json()
    assert stepped["quarter"] == 4
    assert stepped["selected_city_id"] is not None
    traces = client.get(f"/worlds/{world_id}/traces").json()
    assert traces
    audits = client.get(f"/worlds/{world_id}/audits?quarter=1").json()
    assert audits
    assert audits[0]["private_context_used"]["redacted"] is True
    assert "fields_used" in audits[0]["private_context_used"]
    snapshots = client.get(f"/worlds/{world_id}/snapshots").json()
    assert snapshots["quarters"] == [0, 1, 2, 3, 4]
    snapshot = client.get(f"/worlds/{world_id}/snapshots/1").json()
    assert snapshot["quarter"] == 1
    assert snapshot["agents"]["city_hai_finance"]["private_facts"]["redacted"] is True
    branch = client.post(f"/worlds/{world_id}/branches").json()
    assert branch["parent_id"] == world_id
    exported = client.get(f"/worlds/{world_id}/export")
    assert exported.status_code == 200
    assert exported.headers["content-disposition"].endswith(f'"{world_id}.json"')
    assert exported.json()["agents"]["city_hai_finance"]["private_facts"]["redacted"] is True
    worlds.clear()
    restored = client.get(f"/worlds/{world_id}").json()
    assert restored["quarter"] == 4
    assert len(restored["negotiations"]) == 9
    repository.root = original_root


def test_repository_round_trip(tmp_path):
    repo = WorldRepository(tmp_path)
    created = client.post("/worlds", json={"seed": 12}).json()
    from insidegov.serde import world_from_dict

    repo.save(world_from_dict(created))
    loaded = repo.load(created["id"])
    assert loaded is not None
    assert loaded.seed == 12
