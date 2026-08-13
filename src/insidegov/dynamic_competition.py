from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from .engine import SimulationEngine
from .models import WorldState
from .scenarios import create_full_lifecycle_world

POLICY_VARIANTS = (
    (
        "market_exit",
        "允许市场退出",
        "政府拒绝经营性输血，连续亏损企业退出并释放产能。",
    ),
    (
        "unconditional",
        "持续无条件救助",
        "政府优先稳就业，救助不附带压减产能要求。",
    ),
    (
        "conditional",
        "附条件救助",
        "政府提供有限救助，同时要求压减22%产能和12%岗位。",
    ),
)


def run_dynamic_competition_experiment(
    seed: int = 42,
    quarters: int = 24,
    demand_shock: float = -0.42,
    policy_ids: list[str] | None = None,
    mode: str = "deterministic",
    model_name: str | None = None,
    progress_callback: Callable[[dict[str, Any], object], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    initial_world: WorldState | None = None,
) -> dict:
    """Compare exit and rescue institutions under identical imitation pressure.

    All variants share the same seed, initial world, imitation regime and Q10
    demand shock.  Only the rescue institution changes.
    """
    selected = set(policy_ids or [item[0] for item in POLICY_VARIANTS])
    unknown = selected - {item[0] for item in POLICY_VARIANTS}
    if unknown:
        raise ValueError(f"unknown rescue policy: {', '.join(sorted(unknown))}")
    variants: list[dict] = []
    for policy_id, name, description in POLICY_VARIANTS:
        if policy_id not in selected:
            continue
        if initial_world is not None:
            if len(selected) != 1:
                raise ValueError("a resumed world can only continue one rescue policy")
            world = initial_world
        else:
            world = create_full_lifecycle_world(seed, f"dynamic-{policy_id}-{seed}")
            world.name = f"动态竞争实验 / {name}"
            world.policy_mode = mode
            world.model_name = model_name
            world.imitation_policy = "aggressive"
            world.rescue_policy = policy_id
        engine = SimulationEngine(world)
        if not any(
            item.kind == "demand_shock" and item.target == "market"
            for item in world.interventions
        ):
            engine.intervene("demand_shock", "market", demand_shock, quarter=10)
        for quarter_index in range(world.quarter, quarters):
            if cancel_check and cancel_check():
                raise InterruptedError("public job canceled")
            before_actions = len(world.action_audits)
            before_events = len(world.events)
            engine.step()
            if progress_callback:
                progress_callback({
                    "policy_id": policy_id,
                    "quarter": world.quarter,
                    "quarter_index": quarter_index + 1,
                    "quarters": quarters,
                    "new_audits": len(world.action_audits) - before_actions,
                    "new_events": [asdict(item) for item in world.events[before_events:]],
                }, world)
        final = world.history[-1]
        trajectory = [
            {
                "quarter": item.quarter,
                "employment": item.total_employment,
                "capacity": item.capacity,
                "demand": item.demand,
                "utilization": item.utilization,
                "exited_firms": item.exited_firms,
                "zombie_firms": item.zombie_firms,
                "rescue_spending": item.rescue_spending,
                "imitation_capacity": item.imitation_capacity,
            }
            for item in world.history
            if item.quarter >= 8
        ]
        variants.append({
            "id": policy_id,
            "name": name,
            "description": description,
            "final": {
                **asdict(final),
                "phase": final.phase.value,
                "available_budget": round(
                    sum(city.available_budget for city in world.cities.values()), 3
                ),
                "rescue_spending": round(
                    sum(city.rescue_expenditure for city in world.cities.values()), 3
                ),
                "imitation_projects": sum(
                    item.created_firm_id is not None
                    for item in world.imitation_decisions
                ),
            },
            "trajectory": trajectory,
            "imitation_decisions": [
                asdict(item) for item in world.imitation_decisions
            ],
            "rescue_decisions": [
                asdict(item) for item in world.rescue_decisions
            ],
            "agent_runtime": {
                "providers": sorted({
                    item.provider for item in world.action_audits if item.provider
                }),
                "audited_agent_decisions": len(world.action_audits),
                "fallback_count": sum(bool(item.fallback) for item in world.action_audits),
            },
            "key_events": [
                asdict(item) for item in world.events
                if item.quarter >= 9 and item.kind in {
                    "imitation", "market", "rescue", "exit_review", "exit",
                    "external_shock",
                }
            ][-24:],
        })
    headline_comparison = {}
    for variant in variants:
        final = variant["final"]
        if variant["id"] == "market_exit":
            headline_comparison[variant["id"]] = (
                f"退出 {final['exited_firms']} 家，期末利用率"
                f" {final['utilization']:.1%}，救助支出为0。"
            )
        elif variant["id"] == "unconditional":
            headline_comparison[variant["id"]] = (
                f"保留就业 {final['total_employment']} 人，但形成"
                f" {final['zombie_firms']} 家僵尸企业，累计救助"
                f" {final['rescue_spending']:.1f} 亿元。"
            )
        else:
            headline_comparison[variant["id"]] = (
                f"保留就业 {final['total_employment']} 人，期末利用率"
                f" {final['utilization']:.1%}，未形成僵尸企业。"
            )
    return {
        "schema_version": "1.0",
        "seed": seed,
        "quarters": quarters,
        "agent_runtime": {
            "mode": mode,
            "model_name": model_name,
            "providers": sorted({
                provider for variant in variants
                for provider in variant["agent_runtime"]["providers"]
            }),
            "audited_agent_decisions": sum(
                variant["agent_runtime"]["audited_agent_decisions"]
                for variant in variants
            ),
            "fallback_count": sum(
                variant["agent_runtime"]["fallback_count"] for variant in variants
            ),
            "fixed_for_public_experience": mode == "llm",
        },
        "common_conditions": {
            "imitation_policy": "aggressive",
            "demand_shock_quarter": 10,
            "demand_shock": demand_shock,
            "changed_variable": "rescue_policy",
        },
        "causal_chain": [
            "中标城市产业项目投产并形成可观察成功信号",
            "竞争城市招商局选择模仿，财政规则裁剪项目规模",
            "同类产能集中进入，需求冲击后利用率与利润下降",
            "企业申请救助，招商局、财政局和市领导分别表态",
            "规则引擎执行退出、无条件救助或附条件重组",
            "就业、财政支出、产能出清与僵尸企业出现分化",
        ],
        "variants": variants,
        "headline_comparison": headline_comparison,
        "interpretation_boundary": (
            "这是同一参数世界中的机制压力测试，用于比较制度路径，不代表现实政策效应大小。"
        ),
    }
