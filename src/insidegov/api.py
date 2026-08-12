from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .engine import SimulationEngine
from .experiments import (
    run_comparison,
    run_negotiation_comparison,
    run_negotiation_matrix,
    run_talent_comparison,
    run_talent_matrix,
)
from .models import Event
from .negotiation_engine import NegotiationEngine
from .p2 import (
    CandidateRepository,
    compare_worlds,
    extract_candidate_world,
    grounded_interview,
    parse_intervention,
    render_world_report,
)
from .repository import WorldRepository
from .scenarios import (
    create_full_lifecycle_world,
    create_negotiation_world,
    create_talent_world,
)
from .serde import world_from_dict
from .talent_engine import TalentSimulationEngine


class CreateWorldRequest(BaseModel):
    seed: int = Field(default=42, ge=0)
    name: str = "地方产业发展全生命周期"
    policy_mode: Literal["deterministic", "llm"] = "deterministic"
    model_name: Literal["deepseek-v4-flash", "deepseek-v4-pro"] | None = None


class CreateTalentWorldRequest(BaseModel):
    seed: int = Field(default=42, ge=0)
    name: str = "高校人才与技术对接"
    expression_mode: Literal["formal", "plain"] = "plain"
    interpreter_enabled: bool = False
    policy_mode: Literal["deterministic", "llm"] = "deterministic"
    model_name: Literal["deepseek-v4-flash", "deepseek-v4-pro"] | None = None


class CreateNegotiationWorldRequest(BaseModel):
    seed: int = Field(default=42, ge=0)
    name: str = "政企协商与可执行承诺实验室"
    protocol: Literal["free", "policy_match", "clarify_first", "paraphrase_confirm", "constraints_first", "multi_option", "phased_commitment"] = "clarify_first"
    language_style: Literal["formal", "plain"] = "plain"
    policy_mode: Literal["deterministic", "llm"] = "deterministic"



class StepRequest(BaseModel):
    quarters: int = Field(default=1, ge=1, le=40)


class InterventionRequest(BaseModel):
    kind: Literal["fiscal_shock", "demand_shock", "credibility_boost"]
    target: str
    value: float
    quarter: int | None = None


class NaturalLanguageInterventionRequest(BaseModel):
    text: str = Field(min_length=3, max_length=2000)


class ConfirmInterventionRequest(BaseModel):
    plan_id: str


class HistoricalBranchRequest(BaseModel):
    quarter: int = Field(ge=0, le=40)
    name: str | None = None


class CompareWorldsRequest(BaseModel):
    baseline_world_id: str
    branch_world_id: str


class CounterfactualPairRequest(BaseModel):
    quarter: int = Field(ge=0, le=40)


class SyncWorldsRequest(BaseModel):
    baseline_world_id: str
    branch_world_id: str
    quarters: int = Field(default=1, ge=1, le=40)


class InterviewRequest(BaseModel):
    agent_id: str
    quarter: int | None = Field(default=None, ge=0, le=40)
    question: str = Field(min_length=2, max_length=1000)


class ReportRequest(BaseModel):
    baseline_world_id: str | None = None


class MaterialRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=10, max_length=500_000)


class ParameterConfirmation(BaseModel):
    parameter_id: str
    final_value: float
    provenance: Literal["public_source", "expert_judgment", "demo_assumption", "user_input"]


class ConfirmCandidateRequest(BaseModel):
    parameters: list[ParameterConfirmation]
    seed: int = Field(default=42, ge=0)
    name: str | None = None


class MatrixRequest(BaseModel):
    seeds: list[int] = Field(default_factory=lambda: [11, 23, 42, 57, 89], min_length=2, max_length=20)
    quarters: int = Field(default=16, ge=3, le=40)
    include_llm: bool = True
    llm_timeout: float | None = Field(default=None, ge=5, le=120)
    checkpoint_path: str | None = ".insidegov/checkpoints/p1-matrix.json"
    resume: bool = True


class NegotiationMatrixRequest(BaseModel):
    seeds: list[int] = Field(default_factory=lambda: [11, 23, 42, 57, 89], min_length=2, max_length=20)
    quarters: int = Field(default=2, ge=2, le=10)
    include_llm: bool = False


app = FastAPI(
    title="InsideGov API",
    version="0.3.0",
    description="Reproducible government-business interaction policy laboratory",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "INSIDEGOV_CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
    ).split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
worlds: dict[str, SimulationEngine | NegotiationEngine | TalentSimulationEngine] = {}
repository = WorldRepository()
candidate_repository = CandidateRepository()


def _public_world(world) -> dict:
    result = world.to_dict()
    for agent in result.get("agents", {}).values():
        private = agent.get("private_facts", {})
        agent["private_facts"] = {"redacted": True, "fields": sorted(private)}
    for item in result.get("action_audits", []):
        private = item.get("private_context_used", {})
        item["private_context_used"] = {
            "redacted": True, "fields_used": sorted(private),
        }
    return result


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.3.0"}


@app.get("/capabilities")
def capabilities() -> dict:
    return {
        "persistence": True,
        "branching": True,
        "export": True,
        "llm_available": bool(os.getenv("DEEPSEEK_API_KEY")),
        "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
        "default_model": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        "historical_branching": True,
        "natural_language_interventions": True,
        "grounded_interviews": True,
        "automatic_reports": True,
        "material_candidate_worlds": True,
    }


@app.get("/scenarios")
def scenarios() -> list[dict]:
    return [{
        "id": "full_lifecycle",
        "name": "地方产业发展全生命周期",
        "phases": ["招商竞争", "承诺履约", "产业演化"],
        "description": "三座城市竞争龙头项目，履约历史影响供应链进入，并在需求周期中形成集聚或过剩。",
    }, {
        "id": "talent",
        "name": "高校人才与技术对接",
        "phases": ["需求表达", "政策设计", "多轮协商", "履约兑现"],
        "description": "小企业、高校青年教师与资深教授在信息与激励错位下的对接协商：语言模式与中介平台构成 2x2 反事实实验。",
    }, {
        "id": "negotiation_lab", "name": "政企协商与可执行承诺实验室",
        "phases": ["真实与表面需求", "多轮认知互动", "条件承诺", "履约检验"],
        "description": "同一批企业在七种协议下进行严格反事实协商，比较理解、匹配、财政成本和失败识别。",
    }]


@app.get("/protocols")
def negotiation_protocols() -> list[dict]:
    return [{"id": protocol, "name": name} for protocol, name in (
        ("free", "自由协商"), ("policy_match", "政策匹配"),
        ("clarify_first", "澄清优先"), ("paraphrase_confirm", "复述确认"),
        ("constraints_first", "约束先行"), ("multi_option", "多方案协商"),
        ("phased_commitment", "分阶段承诺"),
    )]


@app.post("/negotiation-worlds")
def create_negotiation_world_endpoint(request: CreateNegotiationWorldRequest) -> dict:
    world_id = f"negotiation-world-{uuid.uuid4().hex[:8]}"
    world = create_negotiation_world(
        request.seed, world_id, request.protocol, request.language_style, request.policy_mode,
    )
    world.name = request.name
    engine = NegotiationEngine(world)
    worlds[world_id] = engine
    repository.save(world)
    return _public_world(world)


@app.post("/talent-worlds")
def create_talent_world_endpoint(request: CreateTalentWorldRequest) -> dict:
    world_id = f"talent-world-{uuid.uuid4().hex[:8]}"
    world = create_talent_world(
        request.seed, world_id,
        expression_mode=request.expression_mode,
        interpreter_enabled=request.interpreter_enabled,
        mode=request.policy_mode,
    )
    world.name = request.name
    engine = TalentSimulationEngine(world)
    if request.policy_mode == "llm" and engine.world.policy_mode != "llm":
        engine._event(
            "model_fallback", "LLM 模式未启用",
            "服务端未检测到 DEEPSEEK_API_KEY，世界已使用确定性认知层创建。",
            severity="warning",
        )
    worlds[world_id] = engine
    repository.save(world)
    return _public_world(world)


@app.get("/worlds")
def list_worlds() -> list[dict]:
    stored = {item["id"]: item for item in repository.list()}
    for engine in worlds.values():
        world = engine.world
        stored[world.id] = {
            "id": world.id, "name": world.name, "quarter": world.quarter,
            "phase": world.phase, "parent_id": world.parent_id,
            "policy_mode": world.policy_mode, "model_name": world.model_name,
        }
    return list(stored.values())


@app.post("/worlds")
def create_world(request: CreateWorldRequest) -> dict:
    world_id = f"world-{uuid.uuid4().hex[:8]}"
    world = create_full_lifecycle_world(request.seed, world_id)
    world.name = request.name
    world.policy_mode = request.policy_mode
    world.model_name = request.model_name
    engine = SimulationEngine(world)
    if request.policy_mode == "llm" and engine.world.policy_mode != "llm":
        engine._event(
            "model_fallback", "LLM 模式未启用",
            "服务端未检测到 DEEPSEEK_API_KEY，世界已使用确定性认知层创建。",
            severity="warning",
        )
    worlds[world_id] = engine
    repository.save(world)
    repository.save_snapshot(world)
    return _public_world(world)


def _get(world_id: str) -> SimulationEngine | NegotiationEngine | TalentSimulationEngine:
    engine = worlds.get(world_id)
    if engine is not None:
        return engine
    world = repository.load(world_id)
    if world is None:
        raise HTTPException(404, "world not found")
    if world.negotiation_records or (world.latent_needs and world.phase.value == "negotiation"):
        engine = NegotiationEngine(world)
    elif world.talents:
        engine = TalentSimulationEngine(world)
    else:
        engine = SimulationEngine(world)
    worlds[world_id] = engine
    return engine


@app.get("/worlds/{world_id}")
def get_world(world_id: str) -> dict:
    return _public_world(_get(world_id).world)


@app.post("/worlds/{world_id}/step")
def step_world(world_id: str, request: StepRequest) -> dict:
    engine = _get(world_id)
    for _ in range(request.quarters):
        engine.step()
        repository.save(engine.world)
        repository.save_snapshot(engine.world)
    return _public_world(engine.world)


@app.post("/worlds/{world_id}/interventions")
def add_intervention(world_id: str, request: InterventionRequest) -> dict:
    engine = _get(world_id)
    if request.kind != "demand_shock" and request.target not in engine.world.cities:
        raise HTTPException(422, "target city not found")
    engine.intervene(request.kind, request.target, request.value, request.quarter)
    repository.save(engine.world)
    return {"accepted": True, "interventions": [asdict(item) for item in engine.world.interventions]}


@app.post("/worlds/{world_id}/branches")
def branch_world(world_id: str) -> dict:
    branch = _get(world_id).branch(f"world-{uuid.uuid4().hex[:8]}")
    worlds[branch.world.id] = branch
    repository.save(branch.world)
    return _public_world(branch.world)


@app.post("/worlds/{world_id}/branches/from-history")
def branch_from_history(world_id: str, request: HistoricalBranchRequest) -> dict:
    _get(world_id)
    snapshot = repository.load_snapshot(world_id, request.quarter)
    if snapshot is None:
        raise HTTPException(404, "world snapshot not found")
    snapshot.parent_id = world_id
    snapshot.branched_from_quarter = request.quarter
    snapshot.id = f"world-{uuid.uuid4().hex[:8]}"
    snapshot.name = request.name or f"{snapshot.name} / Q{request.quarter}反事实分支"
    branch = SimulationEngine(snapshot)
    worlds[snapshot.id] = branch
    repository.save(snapshot)
    repository.save_snapshot(snapshot)
    return _public_world(snapshot)


@app.post("/worlds/{world_id}/intervention-plans")
def draft_intervention(world_id: str, request: NaturalLanguageInterventionRequest) -> dict:
    engine = _get(world_id)
    plan = parse_intervention(request.text, engine.world.quarter)
    engine.world.intervention_plans.append(plan)
    repository.save(engine.world)
    return asdict(plan)


@app.post("/worlds/{world_id}/intervention-plans/confirm")
def confirm_intervention(world_id: str, request: ConfirmInterventionRequest) -> dict:
    engine = _get(world_id)
    plan = next((item for item in engine.world.intervention_plans if item.id == request.plan_id), None)
    if plan is None:
        raise HTTPException(404, "intervention plan not found")
    if plan.status == "confirmed":
        return {"accepted": True, "plan": asdict(plan)}
    if not plan.changes:
        raise HTTPException(422, "plan has no executable changes")
    for change in plan.changes:
        target_parts = change.target.split(".")
        if len(target_parts) != 2:
            raise HTTPException(422, f"unsupported target: {change.target}")
        owner, field = target_parts
        if field == "available_budget" and change.operation == "multiply":
            engine.intervene("budget_multiply", owner, change.value, plan.effective_quarter)
        elif field == "available_budget" and change.operation == "add":
            engine.intervene("budget_add", owner, change.value, plan.effective_quarter)
        elif field == "objective_credibility" and change.operation == "add":
            engine.intervene("credibility_boost", owner, change.value, plan.effective_quarter)
        elif owner == "market" and field == "demand_multiplier" and change.operation == "add":
            engine.intervene("demand_shock", owner, change.value, plan.effective_quarter)
        else:
            raise HTTPException(422, f"unsupported change: {change.target} {change.operation}")
    plan.status = "confirmed"
    repository.save(engine.world)
    return {"accepted": True, "plan": asdict(plan)}


@app.post("/experiments/compare-worlds")
def compare_world_endpoints(request: CompareWorldsRequest) -> dict:
    return compare_worlds(_get(request.baseline_world_id).world, _get(request.branch_world_id).world)


@app.post("/worlds/{world_id}/counterfactual-pairs")
def create_counterfactual_pair(world_id: str, request: CounterfactualPairRequest) -> dict:
    _get(world_id)
    snapshot = repository.load_snapshot(world_id, request.quarter)
    if snapshot is None:
        raise HTTPException(404, "world snapshot not found")
    pair = []
    shared_cognition = None
    for label in ("基线副本", "干预副本"):
        cloned = world_from_dict(snapshot.to_dict())
        cloned.parent_id = world_id
        cloned.branched_from_quarter = request.quarter
        cloned.id = f"world-{uuid.uuid4().hex[:8]}"
        cloned.name = f"{snapshot.name} / Q{request.quarter}{label}"
        engine = SimulationEngine(cloned, cognition=shared_cognition)
        if shared_cognition is None:
            shared_cognition = engine.cognition
        worlds[cloned.id] = engine
        repository.save(cloned)
        repository.save_snapshot(cloned)
        pair.append(_public_world(cloned))
    return {"baseline": pair[0], "branch": pair[1], "quarter": request.quarter}


@app.post("/experiments/sync-worlds")
def sync_worlds(request: SyncWorldsRequest) -> dict:
    baseline = _get(request.baseline_world_id)
    branch = _get(request.branch_world_id)
    if baseline.world.quarter != branch.world.quarter:
        raise HTTPException(422, "worlds must start from the same quarter")
    for _ in range(request.quarters):
        baseline.step()
        branch.step()
        for engine in (baseline, branch):
            repository.save(engine.world)
            repository.save_snapshot(engine.world)
    return {
        "baseline": _public_world(baseline.world),
        "branch": _public_world(branch.world),
        "comparison": compare_worlds(baseline.world, branch.world),
    }


@app.post("/worlds/{world_id}/interviews")
def interview_agent(world_id: str, request: InterviewRequest) -> dict:
    engine = _get(world_id)
    selected = engine.world
    if request.quarter is not None and request.quarter != selected.quarter:
        selected = repository.load_snapshot(world_id, request.quarter)
        if selected is None:
            raise HTTPException(404, "world snapshot not found")
    try:
        return grounded_interview(selected, request.agent_id, request.question)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/worlds/{world_id}/reports")
def generate_world_report(world_id: str, request: ReportRequest) -> Response:
    world = _get(world_id).world
    comparison = None
    if request.baseline_world_id:
        comparison = compare_worlds(_get(request.baseline_world_id).world, world)
    report = render_world_report(world, comparison)
    root = Path(os.getenv("INSIDEGOV_REPORT_DIR", ".insidegov/reports"))
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"world-report-{world.id}.html"
    target.write_text(report, encoding="utf-8")
    return Response(
        report, media_type="text/html",
        headers={
            "Content-Disposition": f'inline; filename="{target.name}"',
            "X-InsideGov-Report-Path": str(target),
        },
    )


@app.post("/materials/candidates")
def create_candidate(request: MaterialRequest) -> dict:
    candidate = extract_candidate_world(request.filename, request.content)
    candidate_repository.save(candidate)
    return asdict(candidate)


@app.get("/materials/candidates/{candidate_id}")
def get_candidate(candidate_id: str) -> dict:
    candidate = candidate_repository.load(candidate_id)
    if candidate is None:
        raise HTTPException(404, "candidate world not found")
    return asdict(candidate)


@app.post("/materials/candidates/{candidate_id}/confirm")
def confirm_candidate(candidate_id: str, request: ConfirmCandidateRequest) -> dict:
    candidate = candidate_repository.load(candidate_id)
    if candidate is None:
        raise HTTPException(404, "candidate world not found")
    confirmations = {item.parameter_id: item for item in request.parameters}
    pending = [item.id for item in candidate.parameters if item.id not in confirmations]
    if pending:
        raise HTTPException(422, f"all parameters require confirmation: {', '.join(pending)}")
    for parameter in candidate.parameters:
        confirmed = confirmations[parameter.id]
        parameter.final_value = confirmed.final_value
        parameter.provenance = confirmed.provenance
        parameter.status = "confirmed"
    candidate.status = "confirmed"
    candidate_repository.save(candidate)
    world_id = f"world-{uuid.uuid4().hex[:8]}"
    world = create_full_lifecycle_world(request.seed, world_id)
    world.name = request.name or f"材料候选世界：{candidate.filename}"
    for parameter in candidate.parameters:
        owner, field = parameter.target.split(".")
        if owner in world.cities and hasattr(world.cities[owner], field):
            setattr(world.cities[owner], field, parameter.final_value)
        world.parameter_provenance[parameter.target] = {
            "evidence": parameter.evidence,
            "suggested_value": parameter.suggested_value,
            "final_value": parameter.final_value,
            "confidence": parameter.confidence,
            "provenance": parameter.provenance,
            "candidate_id": candidate.id,
            "filename": candidate.filename,
        }
    world.events.append(Event(
        quarter=0, kind="material_import", title="材料参数已人工确认",
        detail=f"候选世界 {candidate.id} 的 {len(candidate.parameters)} 个参数完成确认",
        severity="success",
    ))
    engine = SimulationEngine(world)
    worlds[world_id] = engine
    repository.save(world)
    repository.save_snapshot(world)
    result = _public_world(world)
    result["candidate_provenance"] = asdict(candidate)
    return result


@app.get("/worlds/{world_id}/traces")
def traces(world_id: str, limit: int = 50) -> list[dict]:
    return [asdict(item) for item in _get(world_id).world.traces[-limit:]]


@app.get("/worlds/{world_id}/agents")
def agents(world_id: str) -> list[dict]:
    return [{
        "id": agent.id, "name": agent.name, "role": agent.role,
        "owner_id": agent.owner_id, "goals": agent.goals,
        "traits": agent.traits, "memory_count": len(agent.memories),
        "last_reflection": agent.last_reflection,
    } for agent in _get(world_id).world.agents.values()]


def _audit_projection(item, reveal_private: bool = False) -> dict:
    row = asdict(item)
    if not reveal_private:
        row["private_context_used"] = {
            "redacted": True,
            "fields_used": sorted(item.private_context_used),
        }
    return row


@app.get("/worlds/{world_id}/audits")
def action_audits(
    world_id: str,
    quarter: int | None = None,
    agent_id: str | None = None,
    include_private: bool = False,
    limit: int = 200,
) -> list[dict]:
    if include_private and os.getenv("INSIDEGOV_ALLOW_PRIVATE_AUDIT") != "1":
        raise HTTPException(403, "private audit access is disabled")
    items = _get(world_id).world.action_audits
    if quarter is not None:
        items = [item for item in items if item.quarter == quarter]
    if agent_id is not None:
        items = [item for item in items if item.agent_id == agent_id]
    return [_audit_projection(item, include_private) for item in items[-max(1, min(limit, 1000)):]]


@app.get("/worlds/{world_id}/snapshots")
def world_snapshots(world_id: str) -> dict:
    _get(world_id)
    return {"world_id": world_id, "quarters": repository.snapshot_quarters(world_id)}


@app.get("/worlds/{world_id}/snapshots/{quarter}")
def get_world_snapshot(world_id: str, quarter: int) -> dict:
    snapshot = repository.load_snapshot(world_id, quarter)
    if snapshot is None:
        raise HTTPException(404, "world snapshot not found")
    result = snapshot.to_dict()
    for item in result.get("action_audits", []):
        item["private_context_used"] = {
            "redacted": True,
            "fields_used": sorted(item.get("private_context_used", {})),
        }
    for agent in result.get("agents", {}).values():
        agent["private_facts"] = {
            "redacted": True,
            "fields": sorted(agent.get("private_facts", {})),
        }
    return result


@app.get("/worlds/{world_id}/export")
def export_world(world_id: str, include_private: bool = False) -> Response:
    if include_private and os.getenv("INSIDEGOV_ALLOW_PRIVATE_AUDIT") != "1":
        raise HTTPException(403, "private export is disabled")
    world = _get(world_id).world
    content = json.dumps(
        world.to_dict() if include_private else _public_world(world),
        ensure_ascii=False, indent=2,
    )
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{world_id}.json"'},
    )


@app.get("/experiments/comparison")
def comparison(seed: int = 42, quarters: int = 16) -> list[dict]:
    return run_comparison(seed, quarters)


@app.get("/experiments/talent-comparison")
def talent_comparison(seed: int = 42, quarters: int = 16, mode: str = "deterministic") -> list[dict]:
    return run_talent_comparison(seed, quarters, mode=mode)


@app.post("/experiments/talent-matrix")
def talent_experiment_matrix(request: MatrixRequest) -> dict:
    return run_talent_matrix(
        seeds=request.seeds, quarters=request.quarters,
        mode="llm" if request.include_llm else "deterministic",
    )


@app.get("/experiments/negotiation-comparison")
def negotiation_comparison(seed: int = 42, quarters: int = 2) -> list[dict]:
    return run_negotiation_comparison(seed, quarters)


@app.post("/experiments/negotiation-matrix")
def negotiation_experiment_matrix(request: NegotiationMatrixRequest) -> dict:
    return run_negotiation_matrix(
        seeds=request.seeds, quarters=request.quarters,
        mode="llm" if request.include_llm else "deterministic",
    )
