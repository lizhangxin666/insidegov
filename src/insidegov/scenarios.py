from __future__ import annotations

from .models import (
    AgentRole,
    AgentState,
    CityState,
    DepartmentState,
    FirmState,
    FirmType,
    Phase,
    WorldState,
)


def _departments(prefix: str) -> list[DepartmentState]:
    return [
        DepartmentState(f"{prefix}_leader", "市领导", "增长、就业与风险平衡", 0.66, 1.0),
        DepartmentState(f"{prefix}_investment", "招商部门", "促成项目签约落地", 0.82, 0.78),
        DepartmentState(f"{prefix}_finance", "财政部门", "控制财政成本与或有风险", 0.28, 0.86),
        DepartmentState(f"{prefix}_park", "产业园区", "提高土地利用与集聚水平", 0.64, 0.58),
    ]


def create_full_lifecycle_world(seed: int = 42, world_id: str = "baseline") -> WorldState:
    cities = {
        "city_hai": CityState(
            "city_hai", "海州市", 160.0, 82.0, 16.0, 120.0, 560.0, 67.0, 58.0,
            82.0, 72.0, 0.82, 10, 0.36, 0.27, 0.22, _departments("hai")
        ),
        "city_lin": CityState(
            "city_lin", "临江市", 215.0, 126.0, 21.0, 168.0, 430.0, 84.0, 76.0,
            88.0, 63.0, 0.91, 6, 0.31, 0.24, 0.34, _departments("lin")
        ),
        "city_yun": CityState(
            "city_yun", "云麓市", 112.0, 64.0, 11.0, 72.0, 720.0, 55.0, 43.0,
            71.0, 86.0, 0.74, 14, 0.44, 0.32, 0.14, _departments("yun")
        ),
    }
    firms: dict[str, FirmState] = {
        "firm_nova": FirmState(
            "firm_nova", "星澜显示", FirmType.ANCHOR, 180.0, 92.0, 220.0, 2600, 120.0,
            86.0, 0.48, 0.78, 0.83, 0.55, 0.88, 68.0,
            perceived_credibility={city_id: city.objective_credibility for city_id, city in cities.items()},
        )
    }
    supplier_types = [FirmType.SUPPLIER, FirmType.TECHNOLOGY, FirmType.OPPORTUNISTIC]
    for index in range(1, 13):
        kind = supplier_types[(index - 1) % len(supplier_types)]
        firms[f"supplier_{index:02d}"] = FirmState(
            id=f"supplier_{index:02d}",
            name=f"链企 {index:02d}",
            firm_type=kind,
            investment_capacity=12.0 + index * 1.8,
            cash=8.0 + index,
            land_need=12.0 + index * 1.3,
            jobs_capacity=100 + index * 22,
            production_capacity=8.0 + index * 1.5,
            technology=48.0 + index * 2.5,
            policy_sensitivity=0.78 if kind == FirmType.OPPORTUNISTIC else 0.38,
            cluster_sensitivity=0.82 if kind == FirmType.SUPPLIER else 0.58,
            credibility_sensitivity=0.68 if kind == FirmType.TECHNOLOGY else 0.48,
            risk_tolerance=0.4 + (index % 4) * 0.12,
            private_intent=0.55 + (index % 5) * 0.08,
            minimum_utility=58.0 + (index % 3) * 4,
            supplier_of="firm_nova",
            perceived_credibility={city_id: city.objective_credibility for city_id, city in cities.items()},
        )
    agents: dict[str, AgentState] = {}
    for city in cities.values():
        agents[f"{city.id}_leader"] = AgentState(
            id=f"{city.id}_leader", name=f"{city.name}市领导", role=AgentRole.CITY_LEADER,
            owner_id=city.id, goals=["促成高质量项目落地", "兼顾就业与产业升级", "维护长期政府信用"],
            private_facts={"political_horizon": city.leadership_term_remaining, "growth_weight": city.gdp_weight},
            traits={"risk_aversion": city.risk_weight, "short_termism": max(0.1, 1-city.leadership_term_remaining/20), "trust_sensitivity": 0.58},
        )
        agents[f"{city.id}_finance"] = AgentState(
            id=f"{city.id}_finance", name=f"{city.name}财政局", role=AgentRole.FINANCE,
            owner_id=city.id, goals=["控制当期财政支出", "约束隐性债务", "确保承诺可兑现"],
            private_facts={"reserve_floor": round(city.available_budget*0.34, 2), "stress_limit": 0.72},
            traits={"risk_aversion": 0.82, "short_termism": 0.45, "trust_sensitivity": 0.74},
        )
    agents["firm_nova_board"] = AgentState(
        id="firm_nova_board", name="星澜显示董事会", role=AgentRole.ENTERPRISE,
        owner_id="firm_nova", goals=["提高长期投资回报", "降低政策与建设风险", "获得稳定供应链"],
        private_facts={"true_intent": firms["firm_nova"].private_intent, "minimum_utility": firms["firm_nova"].minimum_utility, "second_phase_probability": 0.62},
        traits={"risk_aversion": 0.63, "short_termism": 0.28, "trust_sensitivity": 0.83},
    )
    return WorldState(
        id=world_id,
        name="地方产业发展全生命周期",
        seed=seed,
        quarter=0,
        phase=Phase.RECRUITMENT,
        cities=cities,
        firms=firms,
        agents=agents,
        promises=[],
        negotiations=[],
        events=[],
        traces=[],
        history=[],
        interventions=[],
    )
