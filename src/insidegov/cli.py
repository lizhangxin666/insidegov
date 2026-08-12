from __future__ import annotations

import argparse
import json

from .engine import SimulationEngine
from .experiments import run_comparison, run_experiment_matrix
from .scenarios import create_full_lifecycle_world


def main() -> None:
    parser = argparse.ArgumentParser(description="InsideGov policy laboratory")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the full lifecycle scenario")
    run.add_argument("--quarters", type=int, default=16)
    run.add_argument("--seed", type=int, default=42)
    sub.add_parser("compare", help="run four counterfactual branches")
    matrix = sub.add_parser("matrix", help="run P1 multi-strategy and multi-seed matrix")
    matrix.add_argument("--seeds", default="11,23,42,57,89")
    matrix.add_argument("--quarters", type=int, default=16)
    matrix.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()
    if args.command == "compare":
        print(json.dumps(run_comparison(), ensure_ascii=False, indent=2))
        return
    if args.command == "matrix":
        seeds = [int(item) for item in args.seeds.split(",")]
        print(json.dumps(run_experiment_matrix(
            seeds=seeds, quarters=args.quarters, include_llm=not args.no_llm,
        ), ensure_ascii=False, indent=2))
        return
    engine = SimulationEngine(create_full_lifecycle_world(args.seed))
    engine.run(args.quarters)
    summary = {
        "world": engine.world.name,
        "quarter": engine.world.quarter,
        "selected_city": engine.world.selected_city_id,
        "metrics": engine.world.to_dict()["history"][-1],
        "latest_events": engine.world.to_dict()["events"][-8:],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
