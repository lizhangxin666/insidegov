import json

import httpx

from insidegov.agents import DeepSeekCognition, FinanceAction
from insidegov.scenarios import create_full_lifecycle_world


def test_deepseek_adapter_parses_structured_action_without_world_mutation():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-v4-flash"
        assert "max_tokens" not in payload
        content = json.dumps({
            "subsidy": 8.0, "equity": 10.0, "land_discount": 0.3,
            "credit_support": 20.0, "approval_speed": 0.8,
            "talent_support": 0.7, "rationale": "结构化测试", "evidence": ["本地观察"],
        }, ensure_ascii=False)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cognition = DeepSeekCognition("test-key", client=client)
    world = create_full_lifecycle_world()
    city = world.cities["city_hai"]
    before = city.available_budget
    action = cognition.propose_offer(
        world.agents["city_hai_leader"], city, world.firms["firm_nova"], world, {}, []
    )
    assert action.to_package(city.id).fiscal_cost == 19.6
    assert city.available_budget == before


def test_deepseek_adapter_accepts_custom_request_timeout():
    client = httpx.Client(transport=httpx.MockTransport(lambda _request: httpx.Response(500)))
    cognition = DeepSeekCognition("test-key", client=client, request_timeout=7)
    assert cognition.request_deadline_seconds == 17


def test_deepseek_adapter_retries_empty_structured_output_and_records_diagnostics(tmp_path):
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        content = "" if attempts == 1 else json.dumps({
            "city_id": "city_hai", "confidence": 0.8,
            "rationale": "retry worked", "evidence": [],
        })
        return httpx.Response(200, json={
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": content, "reasoning_content": "thinking"},
            }],
            "usage": {"total_tokens": 10},
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    log_path = tmp_path / "diagnostics.jsonl"
    cognition = DeepSeekCognition(
        "test-key", client=client, structured_retries=2, diagnostics_path=log_path,
    )
    world = create_full_lifecycle_world()
    action = cognition.select_location(
        world.agents["firm_nova_board"], world.firms["firm_nova"],
        {"city_hai": 1.0}, {}, [],
    )
    assert action.city_id == "city_hai"
    assert attempts == 2
    assert [row["outcome"] for row in cognition.diagnostics] == ["retry", "success"]
    assert cognition.diagnostics[0]["reasoning_length"] == 8
    persisted = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert [row["outcome"] for row in persisted] == ["retry", "success"]


def test_deepseek_adapter_repairs_compact_resolution_output():
    def handler(_request: httpx.Request) -> httpx.Response:
        content = json.dumps({
            "resolution": "调整后批准",
            "subsidy": 8,
            "equity": 12,
            "land_discount": 0.3,
            "credit_support": 20,
            "approval_speed": 0.8,
            "talent_support": 0.7,
            "rationale": "压现金，转股权",
        }, ensure_ascii=False)
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    cognition = DeepSeekCognition("test-key", client=client)
    world = create_full_lifecycle_world()
    city = world.cities["city_hai"]
    proposal = cognition.fallback.propose_offer(
        world.agents["city_hai_investment"], city, world.firms["firm_nova"], world, {}, []
    ).to_package(city.id)
    review = FinanceAction(
        approved=False,
        maximum_fiscal_cost=20,
        maximum_subsidy=8,
        maximum_equity=12,
        maximum_credit_support=20,
        maximum_first_period_payment=8,
        concerns=["现金超限"],
        rationale="测试审核",
    )
    action = cognition.resolve_offer(
        world.agents["city_hai_leader"], city, proposal, review,
        {}, [],
    )
    assert action.resolution == "restructured_after_tool_veto"
    assert action.payment_schedule == []
    assert cognition.diagnostics[-1]["repaired"] is True
