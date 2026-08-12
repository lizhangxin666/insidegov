import copy

from fastapi.testclient import TestClient

from insidegov.api import app, candidate_repository, repository, worlds
from insidegov.engine import SimulationEngine
from insidegov.p2 import grounded_interview, parse_intervention
from insidegov.scenarios import create_full_lifecycle_world
from insidegov.serde import world_from_dict

client = TestClient(app)


def test_random_state_survives_serde_and_branch_replay():
    original = SimulationEngine(create_full_lifecycle_world(57, "random-state"))
    original.run(6)
    restored = SimulationEngine(world_from_dict(copy.deepcopy(original.world.to_dict())))
    a = original.branch("branch-a").run(8)
    b = restored.branch("branch-b").run(8)
    assert a.history == b.history
    assert a.events == b.events


def test_natural_language_plan_requires_confirmation():
    plan = parse_intervention(
        "临江市第5季度财政收入下降30%，但上级提供5亿元专项资金，优先保障设备采购", 4
    )
    assert plan.status == "draft"
    assert [(item.operation, item.value) for item in plan.changes] == [
        ("multiply", 0.7), ("add", 5.0),
    ]
    assert plan.promise_priority == "equipment_ordered"
    demand_plan = parse_intervention("市场需求下降32%", 4)
    assert [(item.target, item.operation, item.value) for item in demand_plan.changes] == [
        ("market.demand_multiplier", "add", -0.32),
    ]


def test_historical_branch_interview_report_and_compare(tmp_path, monkeypatch):
    worlds.clear()
    original_root = repository.root
    repository.root = tmp_path / "worlds"
    repository.root.mkdir(parents=True)
    monkeypatch.setenv("INSIDEGOV_REPORT_DIR", str(tmp_path / "reports"))
    created = client.post("/worlds", json={"seed": 57}).json()
    world_id = created["id"]
    client.post(f"/worlds/{world_id}/step", json={"quarters": 6})
    branch = client.post(
        f"/worlds/{world_id}/branches/from-history", json={"quarter": 4}
    ).json()
    assert branch["quarter"] == 4
    assert branch["branched_from_quarter"] == 4
    plan = client.post(
        f"/worlds/{branch['id']}/intervention-plans",
        json={"text": "临江市第5季度财政收入下降30%，但上级提供5亿元专项资金"},
    ).json()
    assert client.post(
        f"/worlds/{branch['id']}/intervention-plans/confirm",
        json={"plan_id": plan["id"]},
    ).status_code == 200
    stepped = client.post(f"/worlds/{branch['id']}/step", json={"quarters": 2}).json()
    assert any(event["title"] == "专项资金到位" for event in stepped["events"])
    interview = client.post(
        f"/worlds/{world_id}/interviews",
        json={"agent_id": "city_lin_finance", "quarter": 1, "question": "为什么否决现金加码？"},
    ).json()
    assert interview["quarter"] == 1
    assert interview["evidence_audit_ids"]
    assert "所选季度之后发生的事件" in interview["knowledge_labels"]["unknown_at_the_time"]
    comparison = client.post("/experiments/compare-worlds", json={
        "baseline_world_id": world_id, "branch_world_id": branch["id"],
    }).json()
    assert "delta" in comparison and "causal_chain" in comparison
    report = client.post(
        f"/worlds/{branch['id']}/reports", json={"baseline_world_id": world_id}
    )
    assert report.status_code == 200
    assert "自动实验报告" in report.text
    repository.root = original_root


def test_counterfactual_pair_stays_identical_without_intervention(tmp_path):
    worlds.clear()
    original_root = repository.root
    repository.root = tmp_path
    created = client.post("/worlds", json={"seed": 89}).json()
    world_id = created["id"]
    client.post(f"/worlds/{world_id}/step", json={"quarters": 6})
    pair = client.post(
        f"/worlds/{world_id}/counterfactual-pairs", json={"quarter": 4}
    ).json()
    result = client.post("/experiments/sync-worlds", json={
        "baseline_world_id": pair["baseline"]["id"],
        "branch_world_id": pair["branch"]["id"], "quarters": 5,
    }).json()
    assert result["comparison"]["delta"] == {
        "employment": 0, "cluster": 0, "credibility": 0.0, "spending": 0.0,
    }
    assert result["baseline"]["history"] == result["branch"]["history"]
    repository.root = original_root


def test_material_candidate_requires_evidence_and_confirmation(tmp_path):
    original_root = candidate_repository.root
    candidate_repository.root = tmp_path / "candidates"
    candidate_repository.root.mkdir(parents=True)
    candidate = client.post("/materials/candidates", json={
        "filename": "临江案例.txt",
        "content": "临江市设立财政专项资金135亿元。当地供应链基础达到62，履约率为81%。",
    }).json()
    assert candidate["parameters"]
    assert any(item["provenance"] == "public_source" for item in candidate["parameters"])
    assert any(item["provenance"] == "demo_assumption" for item in candidate["parameters"])
    confirmations = [{
        "parameter_id": item["id"],
        "final_value": item["suggested_value"],
        "provenance": item["provenance"],
    } for item in candidate["parameters"]]
    created = client.post(
        f"/materials/candidates/{candidate['id']}/confirm",
        json={"parameters": confirmations, "seed": 23},
    )
    assert created.status_code == 200
    world = created.json()
    assert world["cities"]["city_lin"]["available_budget"] == 135
    assert world["candidate_provenance"]["status"] == "confirmed"
    stored = repository.load(world["id"])
    assert stored is not None
    assert stored.parameter_provenance["city_lin.available_budget"]["evidence"]
    candidate_repository.root = original_root


def test_grounded_interview_refuses_to_invent_missing_action():
    world = create_full_lifecycle_world(42, "empty")
    result = grounded_interview(world, "city_lin_finance", "为什么这样做？")
    assert "不能补写原因" in result["answer"]
