from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .calibration import run_calibration_suite
from .engine import SimulationEngine
from .experiments import run_ablation_matrix, run_comparison, run_experiment_matrix
from .repository import WorldRepository
from .scenarios import create_full_lifecycle_world


class CreateWorldRequest(BaseModel):
    seed: int = Field(default=42, ge=0)
    name: str = "地方产业发展全生命周期"
    policy_mode: Literal["deterministic", "llm"] = "deterministic"
    model_name: Literal["deepseek-v4-flash", "deepseek-v4-pro"] | None = None


class StepRequest(BaseModel):
    quarters: int = Field(default=1, ge=1, le=40)


class InterventionRequest(BaseModel):
    kind: Literal["fiscal_shock", "demand_shock", "credibility_boost"]
    target: str
    value: float
    quarter: int | None = None


class MatrixRequest(BaseModel):
    seeds: list[int] = Field(default_factory=lambda: [11, 23, 42, 57, 89], min_length=2, max_length=20)
    quarters: int = Field(default=16, ge=3, le=40)
    include_llm: bool = True


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
worlds: dict[str, SimulationEngine] = {}
repository = WorldRepository()


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
    }


@app.get("/scenarios")
def scenarios() -> list[dict]:
    return [{
        "id": "full_lifecycle",
        "name": "地方产业发展全生命周期",
        "phases": ["招商竞争", "承诺履约", "产业演化"],
        "description": "三座城市竞争龙头项目，履约历史影响供应链进入，并在需求周期中形成集聚或过剩。",
    }]


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
    return world.to_dict()


def _get(world_id: str) -> SimulationEngine:
    engine = worlds.get(world_id)
    if engine is not None:
        return engine
    world = repository.load(world_id)
    if world is None:
        raise HTTPException(404, "world not found")
    engine = SimulationEngine(world)
    worlds[world_id] = engine
    return engine


@app.get("/worlds/{world_id}")
def get_world(world_id: str) -> dict:
    return _get(world_id).world.to_dict()


@app.post("/worlds/{world_id}/step")
def step_world(world_id: str, request: StepRequest) -> dict:
    engine = _get(world_id)
    engine.run(request.quarters)
    repository.save(engine.world)
    return engine.world.to_dict()


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
    return branch.world.to_dict()


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


@app.get("/worlds/{world_id}/export")
def export_world(world_id: str) -> Response:
    content = json.dumps(_get(world_id).world.to_dict(), ensure_ascii=False, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{world_id}.json"'},
    )


@app.get("/experiments/comparison")
def comparison(seed: int = 42, quarters: int = 16) -> list[dict]:
    return run_comparison(seed, quarters)


@app.get("/experiments/ablations")
def ablations(seed: int = 42, quarters: int = 16) -> list[dict]:
    return run_ablation_matrix(seed, quarters)


@app.get("/experiments/calibration")
def calibration() -> list[dict]:
    return run_calibration_suite()


@app.post("/experiments/matrix")
def experiment_matrix(request: MatrixRequest) -> dict:
    return run_experiment_matrix(
        seeds=request.seeds, quarters=request.quarters,
        include_llm=request.include_llm, save_report=True,
    )
