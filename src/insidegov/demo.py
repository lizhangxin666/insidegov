"""One-click, rule-generated competition demonstration bundle."""

from __future__ import annotations

import copy
import uuid
from dataclasses import asdict
from datetime import UTC, datetime

from .cases import create_hefei_nio_world, run_hefei_nio_sensitivity
from .engine import SimulationEngine
from .p2 import compare_worlds
from .repository import WorldRepository
from .serde import world_from_dict


def create_hefei_nio_demo(
    repository: WorldRepository,
    seed: int = 42,
    fiscal_multiplier: float = 0.5,
) -> dict:
    """Run a baseline and a common-random-number fiscal counterfactual to Q16."""

    token = uuid.uuid4().hex[:8]
    root = create_hefei_nio_world(seed, f"demo-hefei-nio-root-{token}")
    root_engine = SimulationEngine(root)
    _save(repository, root_engine)
    for _ in range(3):
        root_engine.step()
        _save(repository, root_engine)

    engines = []
    for label in ("baseline", "fiscal-shock"):
        cloned = world_from_dict(root_engine.world.to_dict())
        cloned.id = f"demo-hefei-nio-{label}-{token}"
        cloned.name = f"2020合肥—蔚来五分钟演示 / {label}"
        cloned.parent_id = root_engine.world.id
        cloned.branched_from_quarter = 3
        engine = SimulationEngine(cloned)
        if label == "fiscal-shock":
            engine.intervene("budget_multiply", "city_lin", fiscal_multiplier, 4)
        _save(repository, engine)
        for _ in range(13):
            engine.step()
            _save(repository, engine)
        engines.append(engine)

    baseline, branch = engines
    return {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "source": "live_deterministic_simulation",
        "seed": seed,
        "common_ancestor_quarter": 3,
        "intervention": {
            "quarter": 4,
            "target": "city_lin.available_budget",
            "operation": "multiply",
            "value": fiscal_multiplier,
        },
        "baseline": baseline.world,
        "branch": branch.world,
        "comparison": compare_worlds(baseline.world, branch.world),
        "replay": _replay(baseline.world, branch.world),
        "sensitivity": run_hefei_nio_sensitivity(seed=seed),
    }


def _save(repository: WorldRepository, engine: SimulationEngine) -> None:
    repository.save(engine.world)
    repository.save_snapshot(engine.world)


def _replay(baseline, branch) -> dict:
    selected_id = baseline.selected_city_id or "city_lin"
    selected_name = baseline.cities[selected_id].name
    meeting = next(
        item for item in reversed(baseline.negotiations)
        if item.city_id == selected_id and item.quarter == 3
    )
    outward = next(
        item for item in reversed(baseline.external_negotiations)
        if item.city_id == selected_id and item.quarter == 3
    )
    audits = [
        item for item in baseline.action_audits
        if item.quarter == 3 and item.agent_id in {
            meeting.proposer_id, meeting.reviewer_id, meeting.coordinator_id,
            "firm_nova_board",
        }
    ]
    baseline_final = baseline.history[-1]
    branch_final = branch.history[-1]
    fund_rows = [asdict(item) for item in baseline.investment_funds.values()]
    return {
        "selected_city_id": selected_id,
        "selected_city_name": selected_name,
        "external_negotiation": asdict(outward),
        "internal_negotiation": asdict(meeting),
        "synthetic_private_audit": [
            {
                "audit_id": item.id,
                "agent_id": item.agent_id,
                "private_context_used": copy.deepcopy(item.private_context_used),
                "observation": copy.deepcopy(item.observation),
                "llm_suggestion": copy.deepcopy(item.llm_suggestion),
                "rule_adjustment": copy.deepcopy(item.rule_adjustment),
                "executed_action": copy.deepcopy(item.executed_action),
                "rationale": item.rationale,
                "reflection": item.reflection,
                "provider": item.provider,
                "fallback": item.fallback,
            }
            for item in audits
        ],
        "funding_partners": fund_rows,
        "promises": [asdict(item) for item in baseline.promises],
        "baseline_outcome": asdict(baseline_final),
        "branch_outcome": asdict(branch_final),
        "causal_events": [
            asdict(item) for item in branch.events
            if item.quarter >= 4 and item.kind in {
                "intervention", "promise", "entry", "milestone"
            }
        ],
        "steps": [
            {"id": "world", "title": "公开事实与模型假设", "quarter": 0},
            {"id": "external", "title": "企业表达与政府澄清", "quarter": 3},
            {"id": "internal", "title": "招商—财政—领导内部会商", "quarter": 3},
            {"id": "contract", "title": "条件承诺与联合基金", "quarter": 3},
            {"id": "delivery", "title": "跨期履约与规则结算", "quarter": 4},
            {"id": "counterfactual", "title": "共同随机条件下的反事实", "quarter": 16},
        ],
    }
