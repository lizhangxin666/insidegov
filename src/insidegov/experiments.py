from __future__ import annotations

from dataclasses import asdict

from .engine import SimulationEngine
from .scenarios import create_full_lifecycle_world


def run_comparison(seed: int = 42, quarters: int = 16) -> list[dict]:
    variants = [
        ("基线", []),
        ("财政冲击", [(4, "fiscal_shock", "city_lin", 0.92)]),
        ("需求下行", [(10, "demand_shock", "market", -0.32)]),
        ("履约保障", [(4, "credibility_boost", "city_lin", 0.10)]),
    ]
    results = []
    for name, interventions in variants:
        engine = SimulationEngine(create_full_lifecycle_world(seed, name))
        for quarter, kind, target, value in interventions:
            engine.intervene(kind, target, value, quarter)
        engine.run(quarters)
        final = asdict(engine.world.history[-1])
        final.update({"name": name, "selected_city": engine.world.selected_city_id})
        results.append(final)
    return results


def run_ablation_matrix(seed: int = 42, quarters: int = 16) -> list[dict]:
    variants = [
        ("完整机制", {}),
        ("无私有信息", {"private_information": False}),
        ("无政府内部治理", {"internal_governance": False}),
        ("无信用扩散", {"credibility_diffusion": False}),
        ("无供应链溢出", {"supplier_spillover": False}),
    ]
    results = []
    for name, disabled in variants:
        world = create_full_lifecycle_world(seed, name)
        world.mechanisms.update(disabled)
        engine = SimulationEngine(world)
        engine.run(quarters)
        final = asdict(engine.world.history[-1])
        final.update({
            "name": name,
            "selected_city": engine.world.selected_city_id,
            "negotiation_rounds": len(engine.world.negotiations),
            "fulfilled_promises": sum(p.status == "fulfilled" for p in engine.world.promises),
        })
        results.append(final)
    return results
