from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from .cases import run_hefei_nio_sensitivity
from .demo import create_hefei_nio_demo
from .due_diligence_experiments import run_due_diligence_matrix
from .dynamic_competition import run_dynamic_competition_experiment
from .engine import SimulationEngine
from .experience import (
    StorySessionRepository,
    conversation_mechanism_catalog,
    create_story_session,
    run_conversation_experience,
    story_manifest,
    story_view,
    take_story_turn,
)
from .experiments import (
    run_comparison,
    run_negotiation_comparison,
    run_negotiation_matrix,
    run_organization_mode_comparison,
    run_talent_comparison,
    run_talent_matrix,
)
from .models import Event
from .negotiation_engine import NegotiationEngine
from .organization import action_catalog_payload, behavior_evidence_payload
from .organizational_calibration import run_hefei_nio_organization_calibration
from .p2 import (
    CandidateRepository,
    compare_worlds,
    extract_candidate_world,
    grounded_interview,
    parse_intervention,
    render_world_report,
)
from .public_jobs import (
    RUNNING_STATUSES,
    TERMINAL_STATUSES,
    PublicJobRepository,
    launch_public_job,
)
from .reporting import ExperimentReportRepository
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
    process_mode: Literal["formal", "informal", "hybrid"] = "hybrid"


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
    due_diligence_program: Literal[
        "protocol_linked", "light_screen", "clarification_only",
        "independent_verification", "red_team", "adaptive_staged",
    ] = "protocol_linked"



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


class DueDiligenceMatrixRequest(BaseModel):
    seeds: list[int] = Field(
        default_factory=lambda: [3, 11, 23, 42, 57, 89, 101, 137],
        min_length=2, max_length=30,
    )
    programs: list[str] = Field(default_factory=lambda: [
        "light_screen", "clarification_only", "independent_verification",
        "red_team", "adaptive_staged",
    ])
    thresholds: list[float] = Field(
        default_factory=lambda: [0.25, 0.35, 0.45, 0.5, 0.55, 0.65, 0.75],
        min_length=2, max_length=20,
    )
    policy_mode: Literal["deterministic", "llm"] = "deterministic"
    model_name: Literal["deepseek-v4-flash", "deepseek-v4-pro"] | None = None


class ConversationExperienceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mechanism_id: str = Field(default="M8", pattern=r"^M[1-8]$")
    event_text: str = Field(
        default="企业融资计划反复调整，但尚未公开说明自筹资金缺口。",
        min_length=3, max_length=2000,
    )
    seed: int = Field(default=42, ge=0)


class StorySessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    player_agent_id: str
    source_world_id: str | None = None
    seed: int = Field(default=42, ge=0)


class PublicCoordinationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    process_mode: Literal["formal", "informal", "hybrid"] = "hybrid"
    seed: int = Field(default=42, ge=0)


class PublicDueDiligenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program: Literal[
        "light_screen", "clarification_only", "independent_verification",
        "red_team", "adaptive_staged",
    ] = "adaptive_staged"
    seed: int = Field(default=42, ge=0)


class PublicDynamicCompetitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: Literal["market_exit", "unconditional", "conditional"] = "conditional"
    seed: int = Field(default=42, ge=0)
    quarters: int = Field(default=16, ge=14, le=24)


class StoryTurnRequest(BaseModel):
    action_id: str
    statement: str = Field(default="", max_length=1000)


class PublicJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene: Literal[
        "coordination", "diligence", "dynamic_competition", "conversation", "story_turn",
    ]
    config: dict = Field(default_factory=dict)


class DemoRequest(BaseModel):
    seed: int = Field(default=42, ge=0)
    fiscal_multiplier: float = Field(default=0.5, ge=0.1, le=1.0)


app = FastAPI(
    title="InsideGov API",
    version="0.6.0",
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
story_session_repository = StorySessionRepository()
experiment_report_repository = ExperimentReportRepository()
public_job_repository = PublicJobRepository()
step_jobs: dict[str, dict] = {}
active_step_job_by_world: dict[str, str] = {}
world_step_guards: dict[str, threading.Lock] = {}
step_job_registry_guard = threading.Lock()


def _public_world(world) -> dict:
    result = world.to_dict()
    if result.get("project_risk_profiles"):
        result["project_risk_profiles"] = {
            firm_id: {
                "redacted": True,
                "fields": sorted(profile),
                "note": "潜在质量仅用于生成证据和事后结果，决策时不可见",
            }
            for firm_id, profile in result["project_risk_profiles"].items()
        }
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
    return {"status": "ok", "version": "0.6.0"}


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
        "multi_step_organization_planning": True,
        "open_action_permission_validation": True,
        "endogenous_opportunity_windows": True,
        "long_term_organization_learning": True,
        "source_backed_organization_calibration": True,
        "material_candidate_worlds": True,
        "guided_demo": True,
        "experiment_report_center": True,
        "joint_investment_funds": True,
        "organization_action_sets": True,
        "city_imitation": True,
        "enterprise_exit": True,
        "government_rescue": True,
        "dynamic_competition_experiment": True,
        "evidence_gated_due_diligence": True,
        "due_diligence_threshold_sensitivity": True,
        "compositional_conversation_experience": True,
        "first_person_story_experience": True,
        "single_authority_experience_world": True,
        "durable_public_jobs": True,
        "resumable_public_job_events": True,
        "public_job_checkpoints": True,
        "process_modes": ["formal", "informal", "hybrid"],
    }


@app.get("/organization/actions")
def organization_actions() -> list[dict[str, object]]:
    return action_catalog_payload()


@app.get("/organization/evidence")
def organization_evidence() -> list[dict[str, str]]:
    return behavior_evidence_payload()


@app.get("/experiments/organization-modes")
def organization_mode_comparison(seed: int = 42, quarters: int = 16) -> list[dict]:
    return run_organization_mode_comparison(seed, quarters)


@app.get("/experiments/dynamic-competition")
def dynamic_competition_experiment(
    seed: int = 42,
    quarters: int = 24,
    demand_shock: float = -0.42,
) -> dict:
    if quarters < 14 or quarters > 40:
        raise HTTPException(400, "quarters must be between 14 and 40")
    if demand_shock >= 0 or demand_shock < -0.8:
        raise HTTPException(400, "demand_shock must be in [-0.8, 0)")
    return run_dynamic_competition_experiment(seed, quarters, demand_shock)


@app.post("/demos/hefei-nio")
def hefei_nio_demo(request: DemoRequest) -> dict:
    bundle = create_hefei_nio_demo(
        repository,
        seed=request.seed,
        fiscal_multiplier=request.fiscal_multiplier,
    )
    bundle["baseline"] = _public_world(bundle["baseline"])
    bundle["branch"] = _public_world(bundle["branch"])
    return bundle


@app.get("/cases/hefei-nio/sensitivity")
def hefei_nio_sensitivity(seed: int = 42, quarters: int = 16) -> dict:
    return run_hefei_nio_sensitivity(seed=seed, quarters=quarters)


@app.get("/cases/hefei-nio/organization-calibration")
def hefei_nio_organization_calibration(
    seeds: str = "11,23,42,57,89",
    modes: str = "formal,informal,hybrid",
    quarters: int = 16,
) -> dict:
    try:
        seed_values = [int(item) for item in seeds.split(",") if item.strip()]
        mode_values = [item.strip() for item in modes.split(",") if item.strip()]
        return run_hefei_nio_organization_calibration(
            seeds=seed_values,
            candidate_modes=mode_values,
            quarters=quarters,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/experiment-reports")
def experiment_reports() -> list[dict]:
    return experiment_report_repository.list()


@app.get("/experiment-reports/{report_id}/download")
def download_experiment_report(report_id: str) -> Response:
    report = experiment_report_repository.load(report_id)
    if report is None:
        raise HTTPException(404, "experiment report not found")
    return Response(
        json.dumps(report, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{report_id}.json"',
        },
    )


@app.get("/experiment-reports/{report_id}/worlds/{world_id}")
def experiment_report_world(report_id: str, world_id: str) -> dict:
    report = experiment_report_repository.load(report_id)
    if report is None:
        raise HTTPException(404, "experiment report not found")
    referenced_worlds = {
        item.get("world_id")
        for group in ("strategy_runs", "ablation_runs")
        for item in report.get(group, [])
    }
    if world_id not in referenced_worlds:
        raise HTTPException(404, "world is not referenced by this report")
    world = experiment_report_repository.load_world(world_id)
    if world is None:
        raise HTTPException(404, "archived matrix world not found")
    worlds[world.id] = SimulationEngine(world)
    return _public_world(world)


@app.get("/experiment-reports/{report_id}")
def experiment_report(report_id: str) -> dict:
    report = experiment_report_repository.load(report_id)
    if report is None:
        raise HTTPException(404, "experiment report not found")
    return report


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


@app.get("/experience/conversation-mechanisms")
def public_conversation_mechanisms() -> list[dict]:
    return conversation_mechanism_catalog()


def _public_llm_model() -> str:
    """Return the fixed public Agent model or fail without a hidden fallback."""
    if not os.getenv("DEEPSEEK_API_KEY"):
        raise HTTPException(
            503,
            "公众体验固定使用 DeepSeek Agent；服务端尚未配置 DEEPSEEK_API_KEY。",
        )
    requested = os.getenv("INSIDEGOV_PUBLIC_MODEL", "deepseek-v4-flash")
    return requested if requested in {"deepseek-v4-flash", "deepseek-v4-pro"} else "deepseek-v4-flash"


def _validate_public_job_config(scene: str, config: dict) -> dict:
    allowed = {
        "coordination": {"process_mode", "seed"},
        "diligence": {"program", "seed"},
        "dynamic_competition": {"policy", "seed", "quarters"},
        "conversation": {"mechanism_id", "event_text", "seed"},
        "story_turn": {"session_id", "action_id", "statement"},
    }[scene]
    unknown = set(config) - allowed
    if unknown:
        raise HTTPException(422, f"公众任务不接受这些参数：{', '.join(sorted(unknown))}")
    if scene == "coordination" and config.get("process_mode", "hybrid") not in {"formal", "informal", "hybrid"}:
        raise HTTPException(422, "未知会商程序")
    if scene == "diligence" and config.get("program", "adaptive_staged") not in {
        "light_screen", "clarification_only", "independent_verification", "red_team", "adaptive_staged",
    }:
        raise HTTPException(422, "未知尽调程序")
    if scene == "dynamic_competition" and config.get("policy", "conditional") not in {
        "market_exit", "unconditional", "conditional",
    }:
        raise HTTPException(422, "未知救助制度")
    if scene == "conversation" and config.get("mechanism_id", "M8") not in {f"M{i}" for i in range(1, 9)}:
        raise HTTPException(422, "未知协商机制")
    if scene == "story_turn" and not {"session_id", "action_id"}.issubset(config):
        raise HTTPException(422, "第一人称回合缺少会话或行动")
    result = dict(config)
    result.setdefault("seed", 42)
    if scene == "dynamic_competition":
        result["quarters"] = min(24, max(14, int(result.get("quarters", 16))))
    return result


def _worker_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _ensure_public_job_worker(job: dict) -> dict:
    if job["status"] in RUNNING_STATUSES and not _worker_alive(job.get("pid")):
        public_job_repository.update(
            job["id"], status="queued", pid=None,
            message="服务已经恢复，正在从最近保存的节点继续。",
        )
        public_job_repository.event(
            job["id"], "job.resuming", job["stage_index"], "正在恢复推演",
            "网页或服务中断没有删除任务，系统将从最近检查点继续。", tone="warning",
        )
        launch_public_job(public_job_repository, job["id"])
        return public_job_repository.get(job["id"], include_result=False)
    return job


@app.post("/experience/jobs", status_code=202)
def create_public_job(request: PublicJobRequest) -> dict:
    model_name = _public_llm_model()
    config = _validate_public_job_config(request.scene, request.config)
    job = public_job_repository.create(request.scene, config, model_name)
    launch_public_job(public_job_repository, job["id"])
    return public_job_repository.get(job["id"], include_result=False)


@app.get("/experience/jobs")
def list_public_jobs(limit: int = 20) -> list[dict]:
    jobs = public_job_repository.list(min(50, max(1, limit)))
    return [_ensure_public_job_worker(job) for job in jobs]


@app.get("/experience/jobs/{job_id}")
def get_public_job(job_id: str) -> dict:
    try:
        job = public_job_repository.get(job_id, include_result=False)
    except KeyError as exc:
        raise HTTPException(404, "推演任务不存在") from exc
    return _ensure_public_job_worker(job)


@app.get("/experience/jobs/{job_id}/events")
def get_public_job_events(job_id: str, after: int = 0) -> list[dict]:
    try:
        public_job_repository.get(job_id, include_result=False)
    except KeyError as exc:
        raise HTTPException(404, "推演任务不存在") from exc
    return public_job_repository.events(job_id, max(0, after))


@app.get("/experience/jobs/{job_id}/stream")
def stream_public_job(job_id: str, after: int = 0) -> StreamingResponse:
    try:
        public_job_repository.get(job_id, include_result=False)
    except KeyError as exc:
        raise HTTPException(404, "推演任务不存在") from exc

    def generate():
        cursor = max(0, after)
        idle_ticks = 0
        while True:
            events = public_job_repository.events(job_id, cursor)
            for item in events:
                cursor = item["sequence"]
                yield f"id: {cursor}\nevent: {item['event_type']}\ndata: {json.dumps(item, ensure_ascii=False)}\n\n"
            job = public_job_repository.get(job_id, include_result=False)
            if job["status"] in TERMINAL_STATUSES and not events:
                yield f"event: terminal\ndata: {json.dumps({'status': job['status']}, ensure_ascii=False)}\n\n"
                return
            idle_ticks += 1
            if idle_ticks % 10 == 0:
                yield f": heartbeat {int(time.time())}\n\n"
            time.sleep(1)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
    })


@app.get("/experience/jobs/{job_id}/result")
def get_public_job_result(job_id: str) -> dict:
    try:
        job = public_job_repository.get(job_id)
    except KeyError as exc:
        raise HTTPException(404, "推演任务不存在") from exc
    if job["status"] != "completed" or job.get("result") is None:
        raise HTTPException(409, "推演尚未完成")
    return job["result"]


@app.post("/experience/jobs/{job_id}/cancel")
def cancel_public_job(job_id: str) -> dict:
    try:
        return public_job_repository.request_cancel(job_id)
    except KeyError as exc:
        raise HTTPException(404, "推演任务不存在") from exc


@app.post("/experience/jobs/{job_id}/retry", status_code=202)
def retry_public_job(job_id: str) -> dict:
    model_name = _public_llm_model()
    try:
        parent = public_job_repository.get(job_id)
    except KeyError as exc:
        raise HTTPException(404, "推演任务不存在") from exc
    if parent["status"] not in {"failed", "canceled", "partial"}:
        raise HTTPException(409, "只有失败、取消或部分完成的任务可以重试")
    job = public_job_repository.create(
        parent["scene"], parent["config"], model_name,
        parent_job_id=parent["id"], attempt=parent["attempt"] + 1,
        checkpoint=parent.get("checkpoint"),
    )
    public_job_repository.event(
        job["id"], "job.retry", 0, "从已保存节点重新开始",
        "此前已经完成的世界状态会保留；无法恢复的当前 Agent 行动将重新生成。",
    )
    launch_public_job(public_job_repository, job["id"])
    return public_job_repository.get(job["id"], include_result=False)


@app.post("/experience/coordination")
def create_public_coordination_experience(request: PublicCoordinationRequest) -> dict:
    model_name = _public_llm_model()
    world_id = f"public-coordination-{uuid.uuid4().hex[:8]}"
    world = create_full_lifecycle_world(request.seed, world_id)
    world.name = "公众体验 · 重大项目会商预演"
    world.policy_mode = "llm"
    world.model_name = model_name
    world.process_mode = request.process_mode
    engine = SimulationEngine(world)
    engine.run(3)
    worlds[world.id] = engine
    repository.save(engine.world)
    repository.save_snapshot(engine.world)
    return _public_world(engine.world)


@app.post("/experience/due-diligence")
def create_public_due_diligence_experience(request: PublicDueDiligenceRequest) -> dict:
    model_name = _public_llm_model()
    return run_due_diligence_matrix(
        seeds=[request.seed],
        programs=[request.program],
        mode="llm",
        model_name=model_name,
    )


@app.post("/experience/dynamic-competition")
def create_public_dynamic_competition_experience(
    request: PublicDynamicCompetitionRequest,
) -> dict:
    model_name = _public_llm_model()
    return run_dynamic_competition_experiment(
        seed=request.seed,
        quarters=request.quarters,
        demand_shock=-0.42,
        policy_ids=[request.policy],
        mode="llm",
        model_name=model_name,
    )


@app.post("/experience/conversations")
def create_conversation_experience(request: ConversationExperienceRequest) -> dict:
    model_name = _public_llm_model()
    try:
        world, report = run_conversation_experience(
            repository=repository,
            mechanism_id=request.mechanism_id,
            event_text=request.event_text,
            seed=request.seed,
            policy_mode="llm",
            model_name=model_name,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    worlds[world.id] = NegotiationEngine(world)
    return report


@app.get("/experience/story-manifest")
def public_story_manifest() -> dict:
    return story_manifest()


@app.post("/experience/story-sessions")
def start_story_session(request: StorySessionRequest) -> dict:
    model_name = _public_llm_model()
    source_engine = None
    if request.source_world_id:
        candidate = _get(request.source_world_id)
        if not isinstance(candidate, SimulationEngine):
            raise HTTPException(400, "第一人称体验目前只支持招商全生命周期世界")
        if candidate.world.policy_mode != "llm":
            raise HTTPException(400, "公众体验只能从 LLM Agent 世界创建故事分支")
        source_engine = candidate
    try:
        branch, session = create_story_session(
            repository=repository,
            sessions=story_session_repository,
            player_agent_id=request.player_agent_id,
            source_engine=source_engine,
            seed=request.seed,
            policy_mode="llm",
            model_name=model_name,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    worlds[branch.world.id] = branch
    return story_view(branch.world, session)


@app.get("/experience/story-sessions/{session_id}")
def get_story_session(session_id: str) -> dict:
    session = story_session_repository.load(session_id)
    if session is None:
        raise HTTPException(404, "story session not found")
    engine = _get(session.world_id)
    if not isinstance(engine, SimulationEngine):
        raise HTTPException(409, "story authority world has incompatible engine")
    if engine.world.policy_mode != "llm":
        raise HTTPException(409, "该会话不是公众 LLM Agent 世界，请重新开始")
    return story_view(engine.world, session)


@app.post("/experience/story-sessions/{session_id}/actions")
def play_story_turn(session_id: str, request: StoryTurnRequest) -> dict:
    session = story_session_repository.load(session_id)
    if session is None:
        raise HTTPException(404, "story session not found")
    engine = _get(session.world_id)
    if not isinstance(engine, SimulationEngine):
        raise HTTPException(409, "story authority world has incompatible engine")
    if engine.world.policy_mode != "llm":
        raise HTTPException(409, "该会话不是公众 LLM Agent 世界，请重新开始")
    guard = world_step_guards.setdefault(session.world_id, threading.Lock())
    if not guard.acquire(blocking=False):
        raise HTTPException(409, "该故事世界正在推进，请等待当前行动完成")
    try:
        return take_story_turn(
            engine=engine,
            session=session,
            sessions=story_session_repository,
            repository=repository,
            action_id=request.action_id,
            statement=request.statement,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        guard.release()


@app.post("/negotiation-worlds")
def create_negotiation_world_endpoint(request: CreateNegotiationWorldRequest) -> dict:
    world_id = f"negotiation-world-{uuid.uuid4().hex[:8]}"
    world = create_negotiation_world(
        request.seed, world_id, request.protocol, request.language_style, request.policy_mode,
    )
    world.name = request.name
    world.due_diligence_program = request.due_diligence_program
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
    world.process_mode = request.process_mode
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
    guard = world_step_guards.setdefault(world_id, threading.Lock())
    if not guard.acquire(blocking=False):
        raise HTTPException(409, "该世界已有推进任务，请等待当前任务完成")
    try:
        engine = _get(world_id)
        for _ in range(request.quarters):
            engine.step()
            repository.save(engine.world)
            repository.save_snapshot(engine.world)
        return _public_world(engine.world)
    finally:
        guard.release()


def _run_step_job(job_id: str, world_id: str, quarters: int, guard: threading.Lock) -> None:
    job = step_jobs[job_id]
    job["status"] = "running"
    job["message"] = "正在生成组织计划和第一批 Agent 行动"
    try:
        engine = _get(world_id)
        for index in range(quarters):
            job["current_quarter_index"] = index + 1
            engine.step()
            repository.save(engine.world)
            repository.save_snapshot(engine.world)
            job["completed_quarters"] = index + 1
        job["status"] = "completed"
        job["message"] = "本轮世界推进完成"
        job["result_quarter"] = engine.world.quarter
    except Exception as exc:  # noqa: BLE001 - long jobs must expose their failure
        job["status"] = "failed"
        job["message"] = "运行失败，世界仍保留在上一已保存季度"
        job["error"] = f"{type(exc).__name__}: {str(exc)[:500]}"
    finally:
        job["finished_at"] = time.time()
        with step_job_registry_guard:
            active_step_job_by_world.pop(world_id, None)
        guard.release()


def _step_job_payload(job_id: str) -> dict:
    job = step_jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "step job not found")
    payload = dict(job)
    elapsed_seconds = round(
        (job.get("finished_at") or time.time()) - job["started_at"], 1
    )
    engine = worlds.get(job["world_id"])
    if engine is not None:
        world = engine.world
        payload.update({
            "world_quarter": world.quarter,
            "phase": str(world.phase.value if hasattr(world.phase, "value") else world.phase),
            "agent_audits": len(world.action_audits),
            "organization_actions": len(world.organization_actions),
            "events": len(world.events),
        })
        if job["status"] == "running":
            if world.action_audits:
                latest = world.action_audits[-1]
                payload["message"] = f"{latest.agent_id} 已完成 {latest.action_type}，正在继续调用模型"
            elif world.organization_actions:
                latest_action = world.organization_actions[-1]
                payload["message"] = f"{latest_action.actor_id} 已选择 {latest_action.action_id}"
            elif elapsed_seconds >= 45:
                payload["message"] = "首批结构化动作仍在等待或重试；单次请求上限为45秒"
            else:
                payload["message"] = "正在等待 DeepSeek 返回首个组织计划（单次最多45秒）"
    payload["elapsed_seconds"] = elapsed_seconds
    return payload


@app.post("/worlds/{world_id}/step-jobs")
def create_step_job(world_id: str, request: StepRequest) -> dict:
    engine = _get(world_id)
    with step_job_registry_guard:
        active_id = active_step_job_by_world.get(world_id)
        if active_id and step_jobs.get(active_id, {}).get("status") in {"queued", "running"}:
            return _step_job_payload(active_id)
        guard = world_step_guards.setdefault(world_id, threading.Lock())
        if not guard.acquire(blocking=False):
            raise HTTPException(409, "该世界已有旧版推进请求；请等待完成或重启开发服务")
        job_id = f"step-{uuid.uuid4().hex[:10]}"
        step_jobs[job_id] = {
            "id": job_id, "world_id": world_id, "status": "queued",
            "quarters": request.quarters, "completed_quarters": 0,
            "current_quarter_index": 0, "start_quarter": engine.world.quarter,
            "started_at": time.time(), "finished_at": None,
            "message": "任务已进入后台队列", "error": None,
        }
        active_step_job_by_world[world_id] = job_id
    worker = threading.Thread(
        target=_run_step_job,
        args=(job_id, world_id, request.quarters, guard),
        name=f"insidegov-{job_id}", daemon=True,
    )
    worker.start()
    return _step_job_payload(job_id)


@app.get("/step-jobs/{job_id}")
def get_step_job(job_id: str) -> dict:
    return _step_job_payload(job_id)


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


@app.get("/experiments/due-diligence")
def due_diligence_experiment() -> dict:
    return run_due_diligence_matrix()


@app.post("/experiments/due-diligence-matrix")
def due_diligence_experiment_matrix(request: DueDiligenceMatrixRequest) -> dict:
    try:
        return run_due_diligence_matrix(
            seeds=request.seeds,
            programs=request.programs,
            thresholds=request.thresholds,
            mode=request.policy_mode,
            model_name=request.model_name,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
