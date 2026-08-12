from __future__ import annotations

from .models import (
    AgentRole,
    AgentState,
    CityState,
    DecisionTrace,
    DepartmentState,
    Event,
    FirmState,
    FirmType,
    Intervention,
    MemoryRecord,
    MetricsSnapshot,
    NegotiationRound,
    PaymentTranche,
    Phase,
    PolicyPackage,
    Promise,
    PromiseStatus,
    WorldState,
)


def _offer(data: dict | None) -> PolicyPackage | None:
    if not data:
        return None
    item = dict(data)
    item["payment_schedule"] = [PaymentTranche(**row) for row in item.get("payment_schedule", [])]
    return PolicyPackage(**item)


def world_from_dict(data: dict) -> WorldState:
    cities = {}
    for city_id, raw in data["cities"].items():
        item = dict(raw)
        item["departments"] = [DepartmentState(**d) for d in item["departments"]]
        item["active_offer"] = _offer(item.get("active_offer"))
        cities[city_id] = CityState(**item)
    firms = {}
    for firm_id, raw in data["firms"].items():
        item = dict(raw)
        item["firm_type"] = FirmType(item["firm_type"])
        item["observed_offers"] = {key: _offer(value) for key, value in item["observed_offers"].items()}
        firms[firm_id] = FirmState(**item)
    agents = {}
    for agent_id, raw in data.get("agents", {}).items():
        item = dict(raw)
        item["role"] = AgentRole(item["role"])
        item["memories"] = [MemoryRecord(**m) for m in item.get("memories", [])]
        agents[agent_id] = AgentState(**item)
    for city in cities.values():
        investment_id = f"{city.id}_investment"
        if investment_id not in agents:
            agents[investment_id] = AgentState(
                id=investment_id, name=f"{city.name}招商局", role=AgentRole.INVESTMENT,
                owner_id=city.id,
                goals=["争取龙头项目签约", "提高政策包吸引力", "完成招商任务"],
                private_facts={"signing_target": 1.0, "cash_preference": 0.6, "competitive_intensity": 0.7},
                traits={"risk_aversion": 0.24, "short_termism": 0.78, "trust_sensitivity": 0.42},
            )
    return WorldState(
        id=data["id"], name=data["name"], seed=data["seed"], quarter=data["quarter"],
        phase=Phase(data["phase"]), cities=cities, firms=firms, agents=agents,
        promises=[Promise(**{**p, "status": PromiseStatus(p["status"])}) for p in data.get("promises", [])],
        negotiations=[NegotiationRound(**{
            **n,
            "payment_schedule": [PaymentTranche(**row) for row in n.get("payment_schedule", [])],
        }) for n in data.get("negotiations", [])],
        events=[Event(**e) for e in data.get("events", [])],
        traces=[DecisionTrace(**t) for t in data.get("traces", [])],
        history=[MetricsSnapshot(**{**h, "phase": Phase(h["phase"])}) for h in data.get("history", [])],
        interventions=[Intervention(**i) for i in data.get("interventions", [])],
        market_demand=data.get("market_demand", 100.0), demand_multiplier=data.get("demand_multiplier", 1.0),
        market_price=data.get("market_price", 1.0), selected_city_id=data.get("selected_city_id"),
        parent_id=data.get("parent_id"), policy_mode=data.get("policy_mode", "deterministic"),
        model_name=data.get("model_name"),
        mechanisms=data.get("mechanisms", {
            "private_information": True, "internal_governance": True,
            "credibility_diffusion": True, "supplier_spillover": True,
        }),
    )
