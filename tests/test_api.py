from fastapi.testclient import TestClient

from insidegov.api import app, worlds

client = TestClient(app)


def test_create_step_branch_and_trace():
    worlds.clear()
    created = client.post("/worlds", json={"seed": 11}).json()
    world_id = created["id"]
    stepped = client.post(f"/worlds/{world_id}/step", json={"quarters": 4}).json()
    assert stepped["quarter"] == 4
    assert stepped["selected_city_id"] is not None
    traces = client.get(f"/worlds/{world_id}/traces").json()
    assert traces
    branch = client.post(f"/worlds/{world_id}/branches").json()
    assert branch["parent_id"] == world_id
