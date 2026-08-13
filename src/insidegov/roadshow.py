"""Live roadshow workflows built on the source-backed Hefei–NIO world."""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from .cases import create_hefei_nio_world
from .demo import create_hefei_nio_demo
from .engine import SimulationEngine
from .p2 import compare_worlds
from .repository import WorldRepository
from .serde import world_from_dict

PRESSURE_SCENARIOS: dict[str, dict[str, Any]] = {
    "fiscal_contraction": {
        "name": "财政收缩",
        "question": "如果Q4可用财力下降50%，已签承诺还能兑现吗？",
        "interventions": [(4, "budget_multiply", "city_lin", 0.5)],
    },
    "market_downturn": {
        "name": "市场需求下降",
        "question": "如果Q8市场需求下降35%，产能与财政回流会怎样？",
        "interventions": [(8, "demand_shock", "market", -0.35)],
    },
    "enterprise_delay": {
        "name": "企业建设延期",
        "question": "如果Q6企业项目进度倒退24个百分点，兑现节点会怎样变化？",
        "interventions": [(6, "project_progress_shock", "firm_nova", -0.24)],
    },
    "credit_interruption": {
        "name": "信用传播中断",
        "question": "如果政府履约信息无法传到外围供应商，集群还能形成吗？",
        "interventions": [(4, "credibility_diffusion_toggle", "city_lin", 0.0)],
    },
    "superior_policy": {
        "name": "上级政策变化",
        "question": "如果Q4新增15亿元专项支持并提高协调优先级，结果如何？",
        "interventions": [(4, "superior_policy_support", "city_lin", 15.0)],
    },
}


TRAINING_CHOICES: dict[str, dict[str, dict[str, str]]] = {
    "investment": {
        "cash_push": {"name": "现金强攻", "description": "提高现金工具偏好，先争取签约再接受财政审查。"},
        "fund_coalition": {"name": "联合基金", "description": "优先组织多层级产业资本共同投资。"},
        "staged_pilot": {"name": "分阶段试点", "description": "降低首轮现金强度，以条件性承诺换取可执行性。"},
    },
    "finance": {
        "strict_veto": {"name": "严格守底线", "description": "提高财政储备要求，优先避免跨期失信。"},
        "conditional": {"name": "有条件核准", "description": "保留当前底线，允许股权和分期替代现金。"},
        "development": {"name": "发展优先", "description": "降低储备要求，为重大项目释放更多空间。"},
    },
    "leader": {
        "formal": {"name": "正式科层", "description": "按照送审、会签、协调和合同程序推进。"},
        "hybrid": {"name": "混合协调", "description": "正式程序与会前联盟、政策窗口共同发挥作用。"},
        "informal": {"name": "非正式推动", "description": "更多依赖注意力、联盟和机会窗口推动议程。"},
    },
}


def create_roadshow_suite(repository: WorldRepository, seed: int = 42) -> dict[str, Any]:
    """Generate consultation proof and five common-history stress branches."""
    consultation = create_hefei_nio_demo(repository, seed=seed, fiscal_multiplier=0.5)
    root_id = f"roadshow-pressure-root-{uuid.uuid4().hex[:8]}"
    root_engine = SimulationEngine(create_hefei_nio_world(seed, root_id))
    _save(repository, root_engine)
    for _ in range(3):
        root_engine.step()
        _save(repository, root_engine)

    baseline = _clone_engine(root_engine, f"roadshow-pressure-baseline-{uuid.uuid4().hex[:8]}")
    for _ in range(13):
        baseline.step()
        _save(repository, baseline)

    pressure_runs = []
    for scenario_id, scenario in PRESSURE_SCENARIOS.items():
        branch = _clone_engine(root_engine, f"roadshow-pressure-{scenario_id}-{uuid.uuid4().hex[:8]}")
        branch.world.name = f"2020合肥—蔚来压力测试 / {scenario['name']}"
        for quarter, kind, target, value in scenario["interventions"]:
            branch.intervene(kind, target, value, quarter)
        for _ in range(13):
            branch.step()
            _save(repository, branch)
        comparison = compare_worlds(baseline.world, branch.world)
        pressure_runs.append({
            "id": scenario_id,
            "name": scenario["name"],
            "question": scenario["question"],
            "world": branch.world,
            "summary": _world_summary(branch.world),
            "comparison": comparison,
            "interventions": [asdict(item) for item in branch.world.interventions],
            "key_events": [asdict(item) for item in branch.world.events if item.quarter >= 4 and item.kind in {"intervention", "external_shock", "promise", "milestone", "market", "entry"}][-16:],
        })

    return {
        "schema_version": "1.0",
        "source": "live_deterministic_simulation",
        "seed": seed,
        "consultation": consultation,
        "pressure": {
            "common_ancestor_world_id": root_engine.world.id,
            "common_ancestor_quarter": 3,
            "baseline": baseline.world,
            "baseline_summary": _world_summary(baseline.world),
            "runs": pressure_runs,
        },
        "training_choices": TRAINING_CHOICES,
    }


def run_training_choice(
    repository: WorldRepository,
    role: str,
    strategy: str,
    seed: int = 42,
) -> dict[str, Any]:
    if role not in TRAINING_CHOICES or strategy not in TRAINING_CHOICES[role]:
        raise ValueError("unsupported training role or strategy")
    world = create_hefei_nio_world(seed, f"roadshow-training-{role}-{strategy}-{uuid.uuid4().hex[:8]}")
    choice = TRAINING_CHOICES[role][strategy]
    _apply_training_choice(world, role, strategy)
    world.name = f"干部协调训练 / {choice['name']}"
    engine = SimulationEngine(world)
    _save(repository, engine)
    for _ in range(16):
        engine.step()
        _save(repository, engine)
    final_meeting = next((item for item in reversed(engine.world.negotiations) if item.city_id == "city_lin"), None)
    outward = next((item for item in reversed(engine.world.external_negotiations) if item.city_id == "city_lin"), None)
    return {
        "source": "live_deterministic_simulation",
        "role": role,
        "strategy": strategy,
        "choice": choice,
        "world": engine.world,
        "short_term": {
            "selected_city": engine.world.cities[engine.world.selected_city_id].name if engine.world.selected_city_id else None,
            "enterprise_response": outward.enterprise_response if outward else "no_offer",
            "utility": outward.utility if outward else None,
            "minimum_utility": outward.minimum_utility if outward else None,
            "finance_approved": final_meeting.finance_approved if final_meeting else None,
            "proposal_cost": final_meeting.proposal_cost if final_meeting else None,
            "final_cost": final_meeting.final_cost if final_meeting else None,
            "conflicts": final_meeting.concerns if final_meeting else [],
            "turns": final_meeting.turns if final_meeting else [],
        },
        "long_term": _world_summary(engine.world),
        "audit_count": len(engine.world.action_audits),
        "organization_action_count": len(engine.world.organization_actions),
    }


def _apply_training_choice(world, role: str, strategy: str) -> None:
    if role == "investment":
        facts = world.agents["city_lin_investment"].private_facts
        if strategy == "cash_push":
            facts.update({"cash_preference": 0.92, "competitive_intensity": 0.98, "external_fund_target": 20.0})
        elif strategy == "fund_coalition":
            facts.update({"cash_preference": 0.22, "competitive_intensity": 0.88, "external_fund_target": 53.52})
        else:
            facts.update({"cash_preference": 0.08, "competitive_intensity": 0.60, "external_fund_target": 35.0})
    elif role == "finance":
        facts = world.agents["city_lin_finance"].private_facts
        reserve = {"strict_veto": 125.0, "conditional": 86.0, "development": 58.0}[strategy]
        facts["reserve_floor"] = reserve
    elif role == "leader":
        world.process_mode = strategy


def _clone_engine(root: SimulationEngine, world_id: str) -> SimulationEngine:
    cloned = world_from_dict(root.world.to_dict())
    cloned.id = world_id
    cloned.parent_id = root.world.id
    cloned.branched_from_quarter = 3
    return SimulationEngine(cloned)


def _save(repository: WorldRepository, engine: SimulationEngine) -> None:
    repository.save(engine.world)
    repository.save_snapshot(engine.world)


def _world_summary(world) -> dict[str, Any]:
    latest = world.history[-1]
    selected = world.cities.get(world.selected_city_id) if world.selected_city_id else None
    promises = [item for item in world.promises if item.city_id == world.selected_city_id]
    return {
        "quarter": world.quarter,
        "selected_city": selected.name if selected else None,
        "employment": latest.total_employment,
        "cluster": latest.cluster_size,
        "credibility": selected.objective_credibility if selected else latest.average_credibility,
        "spending": latest.total_committed_expenditure,
        "demand": latest.demand,
        "utilization": latest.utilization,
        "fulfilled_promises": sum(item.status.value == "fulfilled" for item in promises),
        "delayed_promises": sum(item.status.value == "delayed" for item in promises),
        "operating": world.firms["firm_nova"].operating,
    }
