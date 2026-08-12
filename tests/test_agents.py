import json

import httpx

from insidegov.agents import DeepSeekCognition
from insidegov.scenarios import create_full_lifecycle_world


def test_deepseek_adapter_parses_structured_action_without_world_mutation():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat/completions"
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-v4-flash"
        assert payload["max_tokens"] == 900
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
