from __future__ import annotations

from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .engine import SimulationEngine
from .experiments import run_comparison
from .scenarios import create_full_lifecycle_world


class CreateWorldRequest(BaseModel):
    seed: int = Field(default=42, ge=0)
    name: str = "地方产业发展全生命周期"


class StepRequest(BaseModel):
    quarters: int = Field(default=1, ge=1, le=40)


class InterventionRequest(BaseModel):
    kind: str
    target: str
    value: float
    quarter: int | None = None


app = FastAPI(
    title="InsideGov API",
    version="0.1.0",
    description="Reproducible government-business interaction policy laboratory",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
worlds: dict[str, SimulationEngine] = {}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": "0.1.0"}


@app.get("/scenarios")
def scenarios() -> list[dict]:
    return [{
        "id": "full_lifecycle",
        "name": "地方产业发展全生命周期",
        "phases": ["招商竞争", "承诺履约", "产业演化"],
        "description": "三座城市竞争龙头项目，履约历史影响供应链进入，并在需求周期中形成集聚或过剩。",
    }]


@app.post("/worlds")
def create_world(request: CreateWorldRequest) -> dict:
    world_id = f"world-{len(worlds)+1:03d}"
    world = create_full_lifecycle_world(request.seed, world_id)
    world.name = request.name
    worlds[world_id] = SimulationEngine(world)
    return world.to_dict()


def _get(world_id: str) -> SimulationEngine:
    engine = worlds.get(world_id)
    if engine is None:
        raise HTTPException(404, "world not found")
    return engine


@app.get("/worlds/{world_id}")
def get_world(world_id: str) -> dict:
    return _get(world_id).world.to_dict()


@app.post("/worlds/{world_id}/step")
def step_world(world_id: str, request: StepRequest) -> dict:
    return _get(world_id).run(request.quarters).to_dict()


@app.post("/worlds/{world_id}/interventions")
def add_intervention(world_id: str, request: InterventionRequest) -> dict:
    engine = _get(world_id)
    engine.intervene(request.kind, request.target, request.value, request.quarter)
    return {"accepted": True, "interventions": [asdict(item) for item in engine.world.interventions]}


@app.post("/worlds/{world_id}/branches")
def branch_world(world_id: str) -> dict:
    branch = _get(world_id).branch(f"world-{len(worlds)+1:03d}")
    worlds[branch.world.id] = branch
    return branch.world.to_dict()


@app.get("/worlds/{world_id}/traces")
def traces(world_id: str, limit: int = 50) -> list[dict]:
    return [asdict(item) for item in _get(world_id).world.traces[-limit:]]


@app.get("/experiments/comparison")
def comparison(seed: int = 42, quarters: int = 16) -> list[dict]:
    return run_comparison(seed, quarters)

