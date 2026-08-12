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
    Phase,
    PolicyPackage,
    Promise,
    PromiseStatus,
    WorldState,
)


def _offer(data: dict | None) -> PolicyPackage | None:
    return PolicyPackage(**data) if data else None


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
    return WorldState(
        id=data["id"], name=data["name"], seed=data["seed"], quarter=data["quarter"],
        phase=Phase(data["phase"]), cities=cities, firms=firms, agents=agents,
        promises=[Promise(**{**p, "status": PromiseStatus(p["status"])}) for p in data.get("promises", [])],
        negotiations=[NegotiationRound(**n) for n in data.get("negotiations", [])],
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
