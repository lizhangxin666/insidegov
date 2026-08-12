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
    branch = client.post(f"/worlds/{world_id}/branches").json()
    assert branch["parent_id"] == world_id
    exported = client.get(f"/worlds/{world_id}/export")
    assert exported.status_code == 200
    assert exported.headers["content-disposition"].endswith(f'"{world_id}.json"')
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
