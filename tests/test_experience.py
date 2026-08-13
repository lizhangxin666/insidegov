from pathlib import Path

from fastapi.testclient import TestClient

from insidegov.api import app, repository, story_session_repository, worlds
from insidegov.engine import SimulationEngine
from insidegov.experience import (
    StorySessionRepository,
    conversation_mechanism_catalog,
    create_story_session,
    run_conversation_experience,
    story_view,
    take_story_turn,
)
from insidegov.repository import WorldRepository

client = TestClient(app)


def test_conversation_mechanisms_are_composed_and_use_authority_world(tmp_path):
    catalog = conversation_mechanism_catalog()
    assert [item["id"] for item in catalog] == [f"M{i}" for i in range(1, 9)]
    assert len({tuple(item["dimensions"].values()) for item in catalog}) == 8

    repo = WorldRepository(tmp_path / "worlds")
    world, report = run_conversation_experience(
        repo, "M8", "企业融资计划反复调整，自筹资金证明待补充。", seed=42,
    )
    assert report["authority_engine"] == "InsideGov.NegotiationEngine"
    assert report["world_id"] == world.id
    assert repo.load(world.id) is not None
    assert report["compiled_event"]["initially_informed_agent_ids"]
    assert report["compiled_event"]["initially_uninformed_agent_ids"]
    assert report["timeline"]
    assert report["audit_count"] > 0
    assert world.project_risk_profiles["firm_risky"].financing_capacity < 0.3


def test_first_person_turn_is_role_checked_and_settled_by_simulation_engine(tmp_path):
    repo = WorldRepository(tmp_path / "worlds")
    sessions = StorySessionRepository(tmp_path / "stories")
    engine, session = create_story_session(repo, sessions, "city_lin_finance")
    assert isinstance(engine, SimulationEngine)
    before = story_view(engine.world, session)
    allowed = {item["id"] for item in before["available_actions"]}
    assert "risk_assessment" in allowed
    assert "frame_strategic_project" not in allowed

    after = take_story_turn(
        engine, session, sessions, repo,
        "risk_assessment", "请先完成财政风险评估，再讨论报价。",
    )
    assert after["quarter"] == 1
    assert after["receipt"]["status"] == "executed"
    assert after["receipt"]["executed_action"]["action_id"] == "risk_assessment"
    assert after["receipt"]["executed_action"]["selection_provider"] == "first_person_player"
    assert after["receipt"]["new_agent_audits"] > 0
    assert "临江市财政局" in after["narrative"][0]
    assert "财政风险评估" in after["narrative"][0]
    assert repo.load(after["world_id"]) is not None


def test_public_experience_endpoints_require_llm_and_hide_mode_switch(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    worlds.clear()
    original_world_root = repository.root
    original_story_root = story_session_repository.root
    repository.root = Path(tmp_path) / "worlds"
    repository.root.mkdir(parents=True, exist_ok=True)
    story_session_repository.root = Path(tmp_path) / "stories"
    story_session_repository.root.mkdir(parents=True, exist_ok=True)
    try:
        mechanisms = client.get("/experience/conversation-mechanisms")
        assert mechanisms.status_code == 200
        assert len(mechanisms.json()) == 8
        conversation = client.post("/experience/conversations", json={
            "mechanism_id": "M8",
            "event_text": "核心客户名单与订单口径发生变化。",
        })
        assert conversation.status_code == 503
        assert "DEEPSEEK_API_KEY" in conversation.text
        forbidden_switch = client.post("/experience/conversations", json={
            "mechanism_id": "M8",
            "event_text": "核心客户名单与订单口径发生变化。",
            "policy_mode": "deterministic",
        })
        assert forbidden_switch.status_code == 422

        manifest = client.get("/experience/story-manifest")
        assert manifest.status_code == 200
        started = client.post("/experience/story-sessions", json={
            "player_agent_id": "city_lin_finance",
        })
        assert started.status_code == 503
        for endpoint, payload in (
            ("/experience/coordination", {"process_mode": "hybrid"}),
            ("/experience/due-diligence", {"program": "adaptive_staged"}),
            ("/experience/dynamic-competition", {"policy": "conditional"}),
        ):
            response = client.post(endpoint, json=payload)
            assert response.status_code == 503
    finally:
        worlds.clear()
        repository.root = original_world_root
        story_session_repository.root = original_story_root
