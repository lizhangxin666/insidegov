from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from .cases import create_hefei_nio_world, run_hefei_nio_sensitivity
from .demo import create_hefei_nio_demo
from .engine import SimulationEngine
from .experiments import (
    run_comparison,
    run_experiment_matrix,
    run_negotiation_comparison,
    run_negotiation_matrix,
    run_organization_mode_comparison,
    run_talent_comparison,
    run_talent_matrix,
)
from .negotiation_engine import NegotiationEngine
from .organizational_calibration import run_hefei_nio_organization_calibration
from .repository import WorldRepository
from .scenarios import (
    create_full_lifecycle_world,
    create_negotiation_world,
    create_talent_world,
)
from .talent_engine import TalentSimulationEngine


def main() -> None:
    parser = argparse.ArgumentParser(description="InsideGov policy laboratory")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the full lifecycle scenario")
    run.add_argument("--quarters", type=int, default=16)
    run.add_argument("--seed", type=int, default=42)
    run.add_argument("--process-mode", choices=["formal", "informal", "hybrid"], default="hybrid")
    organization_compare = sub.add_parser(
        "organization-compare",
        help="compare formal, informal and hybrid organization processes",
    )
    organization_compare.add_argument("--quarters", type=int, default=16)
    organization_compare.add_argument("--seed", type=int, default=42)
    sub.add_parser("compare", help="run four counterfactual branches")
    matrix = sub.add_parser("matrix", help="run P1 multi-strategy and multi-seed matrix")
    matrix.add_argument("--seeds", default="11,23,42,57,89")
    matrix.add_argument("--quarters", type=int, default=16)
    matrix.add_argument("--no-llm", action="store_true")
    matrix.add_argument(
        "--strategies",
        default=None,
        help=(
            "comma-separated strategy ids; choices: deterministic,"
            "deepseek-v4-flash,deepseek-v4-pro"
        ),
    )
    matrix.add_argument("--llm-timeout", type=float, default=None)
    matrix.add_argument("--checkpoint", default=".insidegov/checkpoints/p1-matrix.json")
    matrix.add_argument("--fresh", action="store_true")

    talent = sub.add_parser("talent", help="run the talent-tech matching scenario")
    talent.add_argument("--quarters", type=int, default=16)
    talent.add_argument("--seed", type=int, default=42)
    talent.add_argument("--language", choices=["formal", "plain"], default="plain")
    talent.add_argument("--platform", action="store_true", help="enable the interpreter platform")
    talent.add_argument("--mode", choices=["deterministic", "llm"], default="deterministic")

    talent_compare = sub.add_parser("talent-compare", help="2x2 counterfactual: language x platform")
    talent_compare.add_argument("--quarters", type=int, default=16)
    talent_compare.add_argument("--seed", type=int, default=42)
    talent_compare.add_argument("--mode", choices=["deterministic", "llm"], default="deterministic")

    talent_matrix = sub.add_parser("talent-matrix", help="multi-seed talent experiment matrix")
    talent_matrix.add_argument("--seeds", default="11,23,42,57,89")
    talent_matrix.add_argument("--quarters", type=int, default=16)
    talent_matrix.add_argument("--mode", choices=["deterministic", "llm"], default="deterministic")
    negotiate = sub.add_parser("negotiate", help="run one government-business negotiation protocol")
    negotiate.add_argument("--protocol", choices=["free", "policy_match", "clarify_first", "paraphrase_confirm", "constraints_first", "multi_option", "phased_commitment"], default="clarify_first")
    negotiate.add_argument("--quarters", type=int, default=2)
    negotiate.add_argument("--seed", type=int, default=42)
    negotiate.add_argument("--language", choices=["formal", "plain"], default="plain")
    negotiate.add_argument("--mode", choices=["deterministic", "llm"], default="deterministic")
    negotiate_compare = sub.add_parser("negotiate-compare", help="compare all seven negotiation protocols")
    negotiate_compare.add_argument("--quarters", type=int, default=2)
    negotiate_compare.add_argument("--seed", type=int, default=42)
    negotiate_matrix = sub.add_parser("negotiate-matrix", help="run the multi-seed negotiation matrix")
    negotiate_matrix.add_argument("--seeds", default="11,23,42,57,89")
    negotiate_matrix.add_argument("--quarters", type=int, default=2)
    case = sub.add_parser("case-hefei-nio", help="run the source-backed 2020 Hefei-NIO case")
    case.add_argument("--quarters", type=int, default=16)
    case.add_argument("--seed", type=int, default=42)
    case.add_argument("--fiscal-shock", type=float, default=0.0, help="optional Q4 available-budget multiplier, e.g. 0.7")
    sensitivity = sub.add_parser(
        "case-hefei-nio-sensitivity",
        help="run 15%%/25%%/35%% fiscal-space sensitivity with and without joint funds",
    )
    sensitivity.add_argument("--quarters", type=int, default=16)
    sensitivity.add_argument("--seed", type=int, default=42)
    behavior_calibration = sub.add_parser(
        "case-hefei-nio-org-calibration",
        help="calibrate organization behavior on pre-deal evidence and validate held-out milestones",
    )
    behavior_calibration.add_argument("--seeds", default="11,23,42,57,89")
    behavior_calibration.add_argument("--quarters", type=int, default=16)
    behavior_calibration.add_argument(
        "--modes", default="formal,informal,hybrid",
        help="comma-separated process modes",
    )
    behavior_calibration.add_argument(
        "--output", default="docs/reports/hefei-nio-organization-calibration",
    )
    demo = sub.add_parser("demo", help="build the complete five-minute demo bundle")
    demo.add_argument("--seed", type=int, default=42)
    demo.add_argument("--fiscal-multiplier", type=float, default=0.5)
    args = parser.parse_args()
    if args.command == "compare":
        print(json.dumps(run_comparison(), ensure_ascii=False, indent=2))
        return
    if args.command == "organization-compare":
        print(json.dumps(
            run_organization_mode_comparison(args.seed, args.quarters),
            ensure_ascii=False, indent=2,
        ))
        return
    if args.command == "matrix":
        seeds = [int(item) for item in args.seeds.split(",")]
        strategies = (
            [item.strip() for item in args.strategies.split(",") if item.strip()]
            if args.strategies else None
        )
        print(json.dumps(run_experiment_matrix(
            seeds=seeds, quarters=args.quarters, include_llm=not args.no_llm,
            strategy_ids=strategies,
            llm_timeout=args.llm_timeout, checkpoint_path=args.checkpoint,
            resume=not args.fresh,
            progress=lambda message: print(f"[matrix] {message}", file=sys.stderr, flush=True),
        ), ensure_ascii=False, indent=2))
        return
    if args.command == "talent":
        world = create_talent_world(
            args.seed, "talent-cli",
            expression_mode=args.language,
            interpreter_enabled=args.platform,
            mode=args.mode,
        )
        engine = TalentSimulationEngine(world)
        engine.run(args.quarters)
        summary = {
            "world": engine.world.name,
            "quarter": engine.world.quarter,
            "expression_mode": engine.world.expression_mode,
            "interpreter_enabled": engine.world.interpreter_enabled,
            "metrics": engine.world.to_dict()["history"][-1],
            "contracts": len(engine.world.talent_contracts),
            "negotiations": len(engine.world.talent_negotiations),
            "latest_events": engine.world.to_dict()["events"][-8:],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return
    if args.command == "talent-compare":
        print(json.dumps(
            run_talent_comparison(args.seed, args.quarters, mode=args.mode),
            ensure_ascii=False, indent=2,
        ))
        return
    if args.command == "talent-matrix":
        seeds = [int(item) for item in args.seeds.split(",")]
        print(json.dumps(run_talent_matrix(
            seeds=seeds, quarters=args.quarters, mode=args.mode,
            progress=lambda message: print(f"[talent-matrix] {message}", file=sys.stderr, flush=True),
        ), ensure_ascii=False, indent=2))
        return
    if args.command == "negotiate":
        world = create_negotiation_world(
            args.seed, "negotiation-cli", args.protocol, args.language, args.mode,
        )
        engine = NegotiationEngine(world)
        engine.run(args.quarters)
        print(json.dumps({
            "world": engine.world.name, "protocol": args.protocol,
            "metrics": engine.world.to_dict()["history"][-1],
            "records": engine.world.to_dict()["negotiation_records"],
        }, ensure_ascii=False, indent=2))
        return
    if args.command == "negotiate-compare":
        print(json.dumps(run_negotiation_comparison(args.seed, args.quarters), ensure_ascii=False, indent=2))
        return
    if args.command == "negotiate-matrix":
        seeds = [int(item) for item in args.seeds.split(",")]
        print(json.dumps(run_negotiation_matrix(seeds, args.quarters), ensure_ascii=False, indent=2))
        return
    if args.command == "case-hefei-nio":
        engine = SimulationEngine(create_hefei_nio_world(args.seed))
        if args.fiscal_shock:
            engine.intervene("budget_multiply", "city_lin", args.fiscal_shock, 4)
        engine.run(args.quarters)
        print(json.dumps({
            "world": engine.world.to_dict(),
            "summary": {
                "selected_city": engine.world.selected_city_id,
                "historical_case": "2020合肥—蔚来",
                "historical_equity_investment": 70.0,
                "simulated_final_offer": (
                    asdict(engine.world.cities["city_lin"].active_offer)
                    if engine.world.cities["city_lin"].active_offer else None
                ),
            },
        }, ensure_ascii=False, indent=2, default=str))
        return
    if args.command == "case-hefei-nio-sensitivity":
        print(json.dumps(
            run_hefei_nio_sensitivity(args.seed, quarters=args.quarters),
            ensure_ascii=False,
            indent=2,
        ))
        return
    if args.command == "case-hefei-nio-org-calibration":
        report = run_hefei_nio_organization_calibration(
            seeds=[int(item) for item in args.seeds.split(",") if item.strip()],
            candidate_modes=[item.strip() for item in args.modes.split(",") if item.strip()],
            quarters=args.quarters,
            output_dir=args.output,
        )
        print(json.dumps({
            "case": report["case"],
            "selected_process_mode": report["selected_process_mode"],
            "selected_mode_quality": report["selected_mode_quality"],
            "mode_summary": report["mode_summary"],
            "report_dir": args.output,
            "limitations": report["limitations"],
        }, ensure_ascii=False, indent=2))
        return
    if args.command == "demo":
        bundle = create_hefei_nio_demo(
            WorldRepository(), args.seed, args.fiscal_multiplier,
        )
        print(json.dumps({
            "generated_at": bundle["generated_at"],
            "source": bundle["source"],
            "baseline_world_id": bundle["baseline"].id,
            "branch_world_id": bundle["branch"].id,
            "comparison": bundle["comparison"],
            "replay": bundle["replay"],
            "sensitivity": bundle["sensitivity"],
        }, ensure_ascii=False, indent=2, default=str))
        return
    world = create_full_lifecycle_world(args.seed)
    world.process_mode = args.process_mode
    engine = SimulationEngine(world)
    engine.run(args.quarters)
    summary = {
        "world": engine.world.name,
        "quarter": engine.world.quarter,
        "selected_city": engine.world.selected_city_id,
        "process_mode": engine.world.process_mode,
        "organization_actions": engine.world.to_dict()["organization_actions"],
        "metrics": engine.world.to_dict()["history"][-1],
        "latest_events": engine.world.to_dict()["events"][-8:],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
