"""Public experience adapters backed by the authoritative InsideGov world.

This module clean-room implements two presentation capabilities inspired by
the supplied G-E conversation and Novel prototypes:

* compositional negotiation protocols and pressure-event visibility;
* first-person, game-like organization turns.

Neither adapter owns a second simulation state.  Conversation runs are normal
``NegotiationEngine`` worlds.  Story sessions point to a normal
``SimulationEngine`` branch and submit role-checked directives into it.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .engine import SimulationEngine
from .models import AgentRole, Event, Phase, WorldState
from .negotiation_agents import CONVERSATION_MECHANISMS
from .negotiation_engine import NegotiationEngine
from .organization import playable_actions
from .repository import WorldRepository
from .scenarios import create_full_lifecycle_world, create_negotiation_world

DIMENSION_LABELS = {
    "mutual_confirmation": "双方确认需求",
    "pre_commitment_consultation": "承诺前会商",
    "conditional_commitment": "书面附条件承诺",
}


def _agent_runtime(world: WorldState) -> dict[str, Any]:
    providers = sorted({item.provider for item in world.action_audits if item.provider})
    return {
        "mode": world.policy_mode,
        "model_name": world.model_name,
        "providers": providers,
        "audited_agent_decisions": len(world.action_audits),
        "fallback_count": sum(bool(item.fallback) for item in world.action_audits),
        "fixed_for_public_experience": world.policy_mode == "llm",
    }


def conversation_mechanism_catalog() -> list[dict[str, Any]]:
    results = []
    for mechanism_id, dimensions in CONVERSATION_MECHANISMS.items():
        enabled = [DIMENSION_LABELS[key] for key, value in dimensions.items() if value]
        disabled = [DIMENSION_LABELS[key] for key, value in dimensions.items() if not value]
        results.append({
            "id": mechanism_id,
            "name": "＋".join(enabled) if enabled else "直接受理与模糊承诺",
            "dimensions": dict(dimensions),
            "enabled": enabled,
            "disabled": disabled,
            "description": "；".join(enabled) if enabled else "不强制追问、前置会商或条件承诺",
        })
    return results


def compile_pressure_event(text: str, firm_id: str = "firm_risky") -> dict[str, Any]:
    """Compile a user condition into a transparent, bounded world change.

    The compiler intentionally supports a small, auditable vocabulary.  It
    never asks an LLM to invent a number and always exposes the applied demo
    assumption to the user before results are interpreted.
    """
    normalized = text.strip() or "企业融资计划反复调整，但尚未公开说明自筹资金缺口。"
    if any(word in normalized for word in ("融资", "自筹", "资金链", "出资")):
        event_type = "financing_stress"
        title = "企业融资能力出现疑点"
        change = {"target": f"{firm_id}.financing_capacity", "operation": "add", "value": -0.18}
        informed = [f"{firm_id}_board"]
        signals = ["融资计划调整", "自筹资金证明仍待补充"]
    elif any(word in normalized for word in ("客户", "订单", "市场", "销量")):
        event_type = "market_validation_stress"
        title = "客户与订单验证出现疑点"
        change = {"target": f"{firm_id}.market_validation", "operation": "add", "value": -0.16}
        informed = [f"{firm_id}_board"]
        signals = ["客户名单口径发生变化", "订单证明有待核验"]
    elif any(word in normalized for word in ("诉讼", "实控人", "治理", "信用")):
        event_type = "governance_stress"
        title = "企业治理与信用出现疑点"
        change = {"target": f"{firm_id}.governance_reliability", "operation": "add", "value": -0.15}
        informed = [f"{firm_id}_board", "city_qing_legal"]
        signals = ["公开登记信息发生变化", "治理材料需要复核"]
    elif any(word in normalized for word in ("财政", "预算", "债务")):
        event_type = "fiscal_tightening"
        title = "地方财政空间收紧"
        change = {"target": "city_qing.available_budget", "operation": "multiply", "value": 0.82}
        informed = ["city_qing_finance"]
        signals = ["预算安排收紧", "大额支持需要重新测算"]
    else:
        event_type = "information_signal"
        title = "项目出现新的不确定信息"
        change = {"target": "none", "operation": "observe", "value": 0.0}
        informed = [f"{firm_id}_board"]
        signals = [normalized[:80]]
    all_agents = {
        "city_qing_investment", "city_qing_finance", "city_qing_legal",
        "city_qing_technical", f"{firm_id}_board",
    }
    return {
        "event_type": event_type,
        "title": title,
        "source_text": normalized,
        "affected_firm_id": firm_id,
        "initially_informed_agent_ids": informed,
        "initially_uninformed_agent_ids": sorted(all_agents - set(informed)),
        "observable_signals": signals,
        "authoritative_change": change,
        "parameter_source": "用户条件＋公开的Demo映射假设",
    }


def _apply_pressure_event(world: WorldState, compiled: dict[str, Any]) -> None:
    change = compiled["authoritative_change"]
    target = str(change["target"])
    value = float(change["value"])
    firm_id = compiled["affected_firm_id"]
    if target.endswith("financing_capacity"):
        profile = world.project_risk_profiles[firm_id]
        profile.financing_capacity = max(0.02, profile.financing_capacity + value)
    elif target.endswith("market_validation"):
        profile = world.project_risk_profiles[firm_id]
        profile.market_validation = max(0.02, profile.market_validation + value)
    elif target.endswith("governance_reliability"):
        profile = world.project_risk_profiles[firm_id]
        profile.governance_reliability = max(0.02, profile.governance_reliability + value)
    elif target == "city_qing.available_budget":
        world.cities["city_qing"].available_budget *= value
    for agent_id in compiled["initially_informed_agent_ids"]:
        if agent_id in world.agents:
            world.agents[agent_id].private_facts["compiled_pressure_signal"] = compiled["source_text"]
    world.events.append(Event(
        quarter=0,
        kind="compiled_pressure_event",
        title=compiled["title"],
        detail=(
            f"{compiled['source_text']}；初始知情方："
            f"{', '.join(compiled['initially_informed_agent_ids'])}；"
            f"可观察信号：{'、'.join(compiled['observable_signals'])}"
        ),
        actor_id=compiled["initially_informed_agent_ids"][0],
        target_id=firm_id,
        severity="warning",
    ))


def run_conversation_experience(
    repository: WorldRepository,
    mechanism_id: str = "M8",
    event_text: str = "企业融资计划反复调整，但尚未公开说明自筹资金缺口。",
    seed: int = 42,
    policy_mode: str = "deterministic",
    model_name: str | None = None,
) -> tuple[WorldState, dict[str, Any]]:
    mechanism_id = mechanism_id.upper()
    catalog = {item["id"]: item for item in conversation_mechanism_catalog()}
    if mechanism_id not in catalog:
        raise ValueError(f"unknown conversation mechanism: {mechanism_id}")
    world_id = f"conversation-{mechanism_id.lower()}-{uuid.uuid4().hex[:8]}"
    world = create_negotiation_world(
        seed=seed, world_id=world_id, protocol=mechanism_id,
        language_style="plain", mode=policy_mode,
    )
    world.name = f"协商压力测试 · {mechanism_id}"
    world.model_name = model_name
    compiled = compile_pressure_event(event_text)
    # Public pressure tests follow one focal project.  Keeping the unrelated
    # seven calibration firms would multiply LLM calls without adding anything
    # to the story the user asked to inspect.
    focus_id = compiled["affected_firm_id"]
    world.firms = {focus_id: world.firms[focus_id]}
    world.latent_needs = {focus_id: world.latent_needs[focus_id]}
    world.stated_needs = {focus_id: world.stated_needs[focus_id]}
    world.gov_beliefs = {focus_id: world.gov_beliefs[focus_id]}
    world.ent_beliefs = {focus_id: world.ent_beliefs[focus_id]}
    world.project_risk_profiles = {focus_id: world.project_risk_profiles[focus_id]}
    _apply_pressure_event(world, compiled)
    engine = NegotiationEngine(world)
    engine.step()
    repository.save(engine.world)
    repository.save_snapshot(engine.world)

    record = next(item for item in engine.world.negotiation_records if item.firm_id == focus_id)
    diligence = next(item for item in engine.world.due_diligence_cases if item.firm_id == focus_id)
    firm = engine.world.firms[focus_id]
    timeline: list[dict[str, Any]] = []
    for item in diligence.agent_turns:
        timeline.append({
            "round": item.get("round"),
            "actor_id": item.get("actor_id", "city_qing_investment"),
            "action": item.get("action_id", "尽调行动"),
            "detail": item.get("rationale", "基于当前证据选择下一项核验"),
            "kind": "evidence",
        })
    for item in record.turns:
        timeline.append({
            "round": item.get("round"),
            "actor_id": item.get("actor", "city_qing_investment"),
            "action": item.get("action", "协商行动"),
            "detail": item.get("rationale") or item.get("text") or item.get("correction") or "形成新的协商状态",
            "kind": "negotiation",
        })
    report = {
        "schema_version": "1.0",
        "world_id": engine.world.id,
        "authority_engine": "InsideGov.NegotiationEngine",
        "agent_runtime": _agent_runtime(engine.world),
        "mechanism": catalog[mechanism_id],
        "compiled_event": compiled,
        "focus_firm": {"id": firm.id, "name": firm.name},
        "result": {
            "decision": diligence.decision,
            "estimated_failure_probability": diligence.estimated_failure_probability,
            "uncertainty": diligence.uncertainty,
            "evidence_count": len(diligence.evidence),
            "elapsed_days": diligence.elapsed_days,
            "negotiation_outcome": record.outcome,
            "fail_reason": record.fail_reason,
            "understanding_gap_before": record.gap_initial,
            "understanding_gap_after": record.gap_final,
            "policy_fit": record.policy_fit,
            "government_cost": record.gov_cost,
        },
        "timeline": timeline,
        "evidence": [asdict(item) for item in diligence.evidence],
        "audit_count": len(engine.world.action_audits),
        "boundary": "结果来自同一个InsideGov权威世界；事件数值为公开的Demo映射假设，不是现实企业评级。",
    }
    return engine.world, report


@dataclass(slots=True)
class StorySession:
    id: str
    source_world_id: str
    world_id: str
    player_agent_id: str
    created_quarter: int
    created_at: str
    updated_at: str
    turn_count: int = 0


class StorySessionRepository:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.getenv(
            "INSIDEGOV_STORY_DIR", ".insidegov/story-sessions",
        ))
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, session: StorySession) -> None:
        target = self.root / f"{session.id}.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(asdict(session), ensure_ascii=False, indent=2), encoding="utf-8",
        )
        temporary.replace(target)

    def load(self, session_id: str) -> StorySession | None:
        target = self.root / f"{session_id}.json"
        if not target.exists():
            return None
        return StorySession(**json.loads(target.read_text(encoding="utf-8")))


STORY_ROLE_IDS = (
    "city_lin_investment", "city_lin_finance", "city_lin_leader", "city_lin_park",
)


def story_manifest() -> dict[str, Any]:
    return {
        "id": "insidegov-first-person",
        "title": "坐进会场",
        "subtitle": "同一个权威世界的第一人称组织博弈",
        "roles": [
            {"id": "city_lin_investment", "name": "临江市招商局", "motive": "争取项目、抢占窗口"},
            {"id": "city_lin_finance", "name": "临江市财政局", "motive": "守住兑现能力与财政底线"},
            {"id": "city_lin_leader", "name": "临江市领导", "motive": "协调冲突并形成可执行方案"},
            {"id": "city_lin_park", "name": "临江市产业园区", "motive": "验证承载条件与产业配套"},
        ],
        "rules": [
            "玩家只能选择角色权限内的行动。",
            "其他组织仍由各自Agent自主行动。",
            "财政、合同、项目与信用后果只由InsideGov规则引擎结算。",
            "每局使用独立世界分支，不会改写原始世界。",
        ],
    }


def create_story_session(
    repository: WorldRepository,
    sessions: StorySessionRepository,
    player_agent_id: str,
    source_engine: SimulationEngine | None = None,
    seed: int = 42,
    policy_mode: str = "deterministic",
    model_name: str | None = None,
) -> tuple[SimulationEngine, StorySession]:
    if player_agent_id not in STORY_ROLE_IDS:
        raise ValueError("该角色暂不属于第一人称体验的可选组织")
    if source_engine is None:
        source_id = f"story-source-{uuid.uuid4().hex[:8]}"
        source_world = create_full_lifecycle_world(seed, source_id)
        source_world.name = "第一人称招商会商"
        source_world.policy_mode = policy_mode
        source_world.model_name = model_name
        source_engine = SimulationEngine(source_world)
        repository.save(source_engine.world)
        repository.save_snapshot(source_engine.world)
    branch = source_engine.branch(f"story-world-{uuid.uuid4().hex[:8]}")
    branch.world.name = f"坐进会场 · {branch.world.agents[player_agent_id].name}"
    now = datetime.now(UTC).isoformat()
    session = StorySession(
        id=f"story-{uuid.uuid4().hex}",
        source_world_id=source_engine.world.id,
        world_id=branch.world.id,
        player_agent_id=player_agent_id,
        created_quarter=branch.world.quarter,
        created_at=now,
        updated_at=now,
    )
    repository.save(branch.world)
    repository.save_snapshot(branch.world)
    sessions.save(session)
    return branch, session


def _level(value: float, low: float, high: float) -> str:
    return "承压" if value < low else "偏强" if value >= high else "不明朗"


def story_view(world: WorldState, session: StorySession, receipt: dict[str, Any] | None = None) -> dict[str, Any]:
    player = world.agents[session.player_agent_id]
    city = world.cities[player.owner_id]
    city_actions = [
        item for item in world.organization_actions if item.city_id == player.owner_id
    ][-10:]
    player_action = next((
        item for item in reversed(city_actions) if item.actor_id == player.id
    ), None)
    recent_actions = ([player_action] if player_action else []) + [
        item for item in reversed(city_actions)
        if player_action is None or item.id != player_action.id
    ][:3]
    recent_events = world.events[-6:]
    private_facts = [
        {"key": key, "value": value}
        for key, value in player.private_facts.items()
    ]
    if player.role != AgentRole.FINANCE:
        private_facts = [item for item in private_facts if "reserve" not in item["key"]]
    narrative = []
    for action in recent_actions:
        narrative.append(
            f"{world.agents.get(action.actor_id, player).name}选择“{action.action_name}”。"
            f"{action.blocked_reason or action.selection_rationale or action.rationale}"
        )
    if not narrative:
        narrative = [
            "最终报价窗口正在缩短。招商、财政、园区和市领导都掌握着不同信息，尚无人知道会议会走向哪里。",
            "你可以先试探边界、补充材料、推动议程，也可以选择一条更谨慎的路径。",
        ]
    return {
        "session_id": session.id,
        "source_world_id": session.source_world_id,
        "world_id": world.id,
        "authority_engine": "InsideGov.SimulationEngine",
        "agent_runtime": _agent_runtime(world),
        "turn": session.turn_count,
        "quarter": world.quarter,
        "phase": world.phase.value,
        "scene_title": (
            "报价窗口前的会商" if world.phase == Phase.RECRUITMENT
            else "承诺兑现进入倒计时" if world.phase == Phase.DELIVERY
            else "产业链开始作出回应"
        ),
        "player": {
            "id": player.id, "name": player.name, "role": player.role.value,
            "goals": player.goals, "private_facts": private_facts,
            "last_reflection": player.last_reflection,
        },
        "signals": [
            {"label": "财政空间", "level": _level(1 - city.fiscal_pressure, 0.35, 0.7)},
            {"label": "组织共识", "level": _level(world.organization_processes[city.id].coalition_support, 0.4, 0.68)},
            {"label": "议程热度", "level": _level(world.organization_processes[city.id].agenda_priority, 0.35, 0.66)},
            {"label": "政府信用", "level": _level(city.objective_credibility, 0.62, 0.82)},
        ],
        "narrative": narrative,
        "recent_events": [asdict(item) for item in recent_events],
        "available_actions": playable_actions(world, player.id),
        "receipt": receipt,
        "world_summary": {
            "selected_city": world.selected_city_id,
            "recruitment_status": world.recruitment_status,
            "organization_actions": len(world.organization_actions),
            "agent_audits": len(world.action_audits),
            "events": len(world.events),
        },
        "boundary": "这是权威世界的角色投影；你看不到其他组织未披露的私有信息。",
    }


def take_story_turn(
    engine: SimulationEngine,
    session: StorySession,
    sessions: StorySessionRepository,
    repository: WorldRepository,
    action_id: str,
    statement: str,
) -> dict[str, Any]:
    allowed = {item["id"] for item in playable_actions(engine.world, session.player_agent_id)}
    if action_id not in allowed:
        raise ValueError("该行动不属于角色权限或当前程序场域")
    directive = {
        "id": f"directive-{uuid.uuid4().hex[:10]}",
        "actor_id": session.player_agent_id,
        "action_id": action_id,
        "statement": statement.strip() or "我决定现在发起这项行动。",
        "urgency": 0.98,
        "execute_quarter": engine.world.quarter + 1,
        "status": "pending",
    }
    action_start = len(engine.world.organization_actions)
    audit_start = len(engine.world.action_audits)
    event_start = len(engine.world.events)
    engine.world.experience_directives.append(directive)
    engine.step()
    new_actions = engine.world.organization_actions[action_start:]
    executed = next((item for item in new_actions if item.actor_id == session.player_agent_id), None)
    directive_status = next(
        item for item in engine.world.experience_directives if item["id"] == directive["id"]
    )
    if directive_status["status"] == "selected" and executed is not None:
        directive_status["status"] = "executed" if executed.authorized else "blocked"
        directive_status["blocked_reason"] = executed.blocked_reason
    session.turn_count += 1
    session.updated_at = datetime.now(UTC).isoformat()
    sessions.save(session)
    repository.save(engine.world)
    repository.save_snapshot(engine.world)
    receipt = {
        "directive_id": directive["id"],
        "requested_action": action_id,
        "status": directive_status["status"],
        "executed_action": asdict(executed) if executed else None,
        "new_agent_audits": len(engine.world.action_audits) - audit_start,
        "new_events": [asdict(item) for item in engine.world.events[event_start:]],
        "rule_statement": "行动先经角色权限和程序场域检查，财政与项目后果随后由规则引擎结算。",
    }
    return story_view(engine.world, session, receipt)
