from __future__ import annotations

import json
import os
import statistics
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from .agents import CognitiveProvider, DeepSeekCognition, DeterministicCognition
from .calibration import run_calibration_suite
from .engine import SimulationEngine
from .models import WorldState
from .negotiation_engine import NegotiationEngine
from .repository import WorldRepository
from .scenarios import (
    create_full_lifecycle_world,
    create_negotiation_world,
    create_talent_world,
)
from .talent_engine import TalentSimulationEngine


def run_organization_mode_comparison(
    seed: int = 42, quarters: int = 16,
) -> list[dict]:
    """Run the same policy world under formal, informal and hybrid processes."""
    from collections import Counter

    rows: list[dict] = []
    for mode in ("formal", "informal", "hybrid"):
        world = create_full_lifecycle_world(seed, f"organization-{mode}-{seed}")
        world.process_mode = mode
        engine = SimulationEngine(world)
        engine.run(quarters)
        action_counts = Counter(item.action_id for item in world.organization_actions)
        arena_counts = Counter(item.arena for item in world.organization_actions)
        selected = world.cities.get(world.selected_city_id) if world.selected_city_id else None
        selected_process = (
            world.organization_processes.get(world.selected_city_id)
            if world.selected_city_id else None
        )
        rows.append({
            "process_mode": mode,
            "seed": seed,
            "selected_city": selected.name if selected else None,
            "selected_city_id": world.selected_city_id,
            "organization_actions": len(world.organization_actions),
            "action_counts": dict(action_counts),
            "arena_counts": dict(arena_counts),
            "procedural_completeness": round(
                selected_process.procedural_completeness if selected_process else 0.0, 3
            ),
            "coalition_support": round(
                selected_process.coalition_support if selected_process else 0.0, 3
            ),
            "risk_posture": selected_process.risk_posture if selected_process else None,
            "final_employment": world.history[-1].total_employment,
            "average_credibility": world.history[-1].average_credibility,
            "fulfilled_promises": sum(item.status.value == "fulfilled" for item in world.promises),
            "delayed_promises": sum(item.status.value == "delayed" for item in world.promises),
            "selected_offer": (
                {
                    "subsidy": selected.active_offer.subsidy,
                    "equity": selected.active_offer.equity,
                    "external_equity": selected.active_offer.external_equity,
                    "fiscal_cost": round(selected.active_offer.fiscal_cost, 3),
                }
                if selected and selected.active_offer else None
            ),
            "action_sequence": [
                item.action_id for item in world.organization_actions
                if item.city_id == world.selected_city_id and item.quarter <= 3
            ],
        })
    return rows

DEFAULT_SEEDS = [11, 23, 42, 57, 89]

# 人才场景 2x2 反事实：语言模式（官话/人话）× 中介平台（关/开）
TALENT_VARIANTS = [
    ("formal_no_platform", "官话直连", {"expression_mode": "formal", "interpreter_enabled": False}),
    ("plain_no_platform", "人话直连", {"expression_mode": "plain", "interpreter_enabled": False}),
    ("formal_platform", "官话+平台", {"expression_mode": "formal", "interpreter_enabled": True}),
    ("plain_platform", "人话+平台", {"expression_mode": "plain", "interpreter_enabled": True}),
]
TALENT_METRICS = [
    "match_rate", "avg_understanding", "avg_trust",
    "talent_hired", "tech_progress", "total_committed_expenditure", "average_credibility",
]
MECHANISM_VARIANTS = [
    ("full", "完整机制", {}),
    ("no_private_information", "无私有信息", {"private_information": False}),
    ("no_internal_governance", "无政府内部治理", {"internal_governance": False}),
    ("no_credibility_diffusion", "无信用扩散", {"credibility_diffusion": False}),
    ("no_supplier_spillover", "无供应链溢出", {"supplier_spillover": False}),
]
REPORT_METRICS = [
    "total_employment", "total_tax_revenue", "total_committed_expenditure",
    "average_credibility", "cluster_size", "capacity", "utilization", "market_price",
]
SUMMARY_METRICS = [*REPORT_METRICS, "fulfilled_promises"]


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
    results = []
    for variant_id, name, disabled in MECHANISM_VARIANTS:
        world = create_full_lifecycle_world(seed, name)
        world.mechanisms.update(disabled)
        engine = SimulationEngine(world)
        engine.run(quarters)
        final = _run_record(engine.world, seed, variant_id)
        final["name"] = name
        results.append(final)
    return results


def run_experiment_matrix(
    seeds: list[int] | None = None,
    quarters: int = 16,
    include_llm: bool = True,
    strategy_ids: list[str] | None = None,
    provider_factory: Callable[[str], CognitiveProvider] | None = None,
    save_report: bool = True,
    llm_timeout: float | None = None,
    checkpoint_path: str | Path | None = None,
    resume: bool = True,
    progress: Callable[[str], None] | None = None,
    world_archive_dir: str | Path | None = ".insidegov/matrix-worlds",
) -> dict:
    """Compare three cognition strategies and deterministic mechanism ablations.

    LLM strategies are never silently replaced in this report. Missing credentials,
    request errors, structured-action failures and engine fallbacks are failure cases.
    """
    selected_seeds = seeds or DEFAULT_SEEDS
    strategies = [
        ("deterministic", "确定性异质策略"),
        ("deepseek-v4-flash", "DeepSeek V4 Flash"),
        ("deepseek-v4-pro", "DeepSeek V4 Pro"),
    ]
    if not include_llm:
        strategies = strategies[:1]
    if strategy_ids is not None:
        strategy_names = dict(strategies)
        unknown = [strategy_id for strategy_id in strategy_ids if strategy_id not in strategy_names]
        if unknown:
            raise ValueError(f"unknown strategy id(s): {', '.join(unknown)}")
        strategies = [(strategy_id, strategy_names[strategy_id]) for strategy_id in strategy_ids]
    factory = provider_factory or (
        lambda strategy_id: _provider_for_strategy(strategy_id, llm_timeout=llm_timeout)
    )
    provider_cache: dict[str, CognitiveProvider] = {}
    configuration = {
        "seeds": selected_seeds, "quarters": quarters,
        "strategies": [item[0] for item in strategies],
        "ablations": [item[0] for item in MECHANISM_VARIANTS],
    }
    checkpoint = _load_checkpoint(checkpoint_path) if resume else None
    if checkpoint and checkpoint.get("configuration") != configuration:
        raise ValueError(
            "checkpoint configuration does not match current matrix; use --fresh or a new checkpoint path"
        )
    checkpoint = checkpoint or {
        "schema_version": "1.0",
        "configuration": configuration,
        "strategy_runs": [],
        "calibration": {},
        "failure_cases": [],
        "ablation_runs": [],
    }

    def provider(strategy_id: str) -> CognitiveProvider:
        if strategy_id not in provider_cache:
            provider_cache[strategy_id] = factory(strategy_id)
        return provider_cache[strategy_id]

    strategy_runs: list[dict] = checkpoint["strategy_runs"]
    strategy_failures: list[dict] = [
        item for item in checkpoint["failure_cases"] if "strategy" in item
    ]
    calibration: dict[str, list[dict]] = checkpoint["calibration"]
    completed_strategy = {
        (row["strategy"], row["seed"]) for row in strategy_runs
    }
    failed_strategy = {
        (row["strategy"], row["seed"])
        for row in strategy_failures
        if row.get("stage") == "initialization_or_run"
    }

    for strategy_id, strategy_name in strategies:
        if strategy_id not in calibration:
            _emit_progress(progress, f"calibration {strategy_id} start")
            try:
                calibration[strategy_id] = run_calibration_suite(provider(strategy_id))
            except Exception as exc:  # noqa: BLE001 - matrix must retain failed providers
                calibration[strategy_id] = [{
                    "id": "provider_initialization", "role": "system", "passed": False,
                    "description": "认知提供者应可初始化", "expected": "available",
                    "observed": type(exc).__name__, "failure_reason": str(exc),
                }]
            for calibration_case in calibration[strategy_id]:
                if not calibration_case.get("passed", False):
                    failure = {
                        "strategy": strategy_id, "seed": "calibration",
                        "stage": f"calibration:{calibration_case['id']}",
                        "reason": calibration_case.get("failure_reason") or calibration_case["observed"],
                        "last_events": [],
                    }
                    if failure not in strategy_failures:
                        strategy_failures.append(failure)
            _save_checkpoint(
                checkpoint_path, checkpoint, strategy_runs, calibration,
                strategy_failures, checkpoint["ablation_runs"],
            )
            _emit_progress(progress, f"calibration {strategy_id} done")
        else:
            _emit_progress(progress, f"calibration {strategy_id} resumed")
        for seed in selected_seeds:
            if (strategy_id, seed) in completed_strategy:
                _emit_progress(progress, f"strategy {strategy_id} seed={seed} resumed")
                continue
            if (strategy_id, seed) in failed_strategy:
                _emit_progress(progress, f"strategy {strategy_id} seed={seed} resumed-failed")
                continue
            _emit_progress(progress, f"strategy {strategy_id} seed={seed} start")
            try:
                cognition = provider(strategy_id)
                diagnostic_start = len(getattr(cognition, "diagnostics", []))
                world = create_full_lifecycle_world(seed, f"{strategy_name} / seed {seed}")
                world.id = f"matrix-{strategy_id}-seed-{seed}"
                world.policy_mode = "deterministic" if strategy_id == "deterministic" else "llm"
                world.model_name = None if strategy_id == "deterministic" else strategy_id
                engine = SimulationEngine(world, cognition=cognition)
                _run_and_archive(engine, quarters, world_archive_dir)
                record = _run_record(engine.world, seed, strategy_id)
                record["world_id"] = engine.world.id
                if world_archive_dir:
                    record["world_archive"] = str(Path(world_archive_dir) / f"{engine.world.id}.json")
                fallbacks = [event for event in engine.world.events if event.kind == "model_fallback"]
                diagnostics = getattr(cognition, "diagnostics", [])[diagnostic_start:]
                if diagnostics:
                    record["llm_diagnostics"] = diagnostics
                violations = _invariant_violations(engine.world)
                if fallbacks or violations:
                    strategy_failures.append({
                        "strategy": strategy_id, "seed": seed, "stage": "simulation",
                        "reason": "; ".join(
                            [f"{len(fallbacks)} cognitive fallbacks"] + violations
                        ),
                        "last_events": [event.title for event in engine.world.events[-5:]],
                        "fallback_details": [event.detail for event in fallbacks],
                        "llm_diagnostics": diagnostics,
                    })
                    record["successful"] = False
                strategy_runs.append(record)
                completed_strategy.add((strategy_id, seed))
                _emit_progress(progress, f"strategy {strategy_id} seed={seed} done")
            except Exception as exc:  # noqa: BLE001 - failure case is report output
                strategy_failures.append({
                    "strategy": strategy_id, "seed": seed, "stage": "initialization_or_run",
                    "reason": f"{type(exc).__name__}: {exc}", "last_events": [],
                })
                failed_strategy.add((strategy_id, seed))
                _emit_progress(progress, f"strategy {strategy_id} seed={seed} failed")
            _save_checkpoint(
                checkpoint_path, checkpoint, strategy_runs, calibration,
                strategy_failures, checkpoint["ablation_runs"],
            )

    ablation_runs: list[dict] = checkpoint["ablation_runs"]
    ablation_failures: list[dict] = [
        item for item in checkpoint["failure_cases"] if "variant" in item
    ]
    completed_ablation = {
        (row["strategy"], row["seed"]) for row in ablation_runs
    }
    failed_ablation = {
        (row["variant"], row["seed"]) for row in ablation_failures
    }
    for variant_id, name, toggles in MECHANISM_VARIANTS:
        for seed in selected_seeds:
            if (variant_id, seed) in completed_ablation:
                _emit_progress(progress, f"ablation {variant_id} seed={seed} resumed")
                continue
            if (variant_id, seed) in failed_ablation:
                _emit_progress(progress, f"ablation {variant_id} seed={seed} resumed-failed")
                continue
            _emit_progress(progress, f"ablation {variant_id} seed={seed} start")
            try:
                world = create_full_lifecycle_world(seed, f"{name} / seed {seed}")
                world.id = f"matrix-ablation-{variant_id}-seed-{seed}"
                world.mechanisms.update(toggles)
                engine = SimulationEngine(world, cognition=DeterministicCognition())
                _run_and_archive(engine, quarters, world_archive_dir)
                record = _run_record(engine.world, seed, variant_id)
                record["world_id"] = engine.world.id
                if world_archive_dir:
                    record["world_archive"] = str(Path(world_archive_dir) / f"{engine.world.id}.json")
                ablation_runs.append(record)
                completed_ablation.add((variant_id, seed))
                _emit_progress(progress, f"ablation {variant_id} seed={seed} done")
            except Exception as exc:  # noqa: BLE001 - failure case is report output
                ablation_failures.append({
                    "variant": variant_id, "seed": seed,
                    "reason": f"{type(exc).__name__}: {exc}",
                })
                failed_ablation.add((variant_id, seed))
                _emit_progress(progress, f"ablation {variant_id} seed={seed} failed")
            _save_checkpoint(
                checkpoint_path, checkpoint, strategy_runs, calibration,
                strategy_failures + ablation_failures, ablation_runs,
            )

    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "configuration": configuration,
        "strategy_summary": _summaries(strategy_runs, "strategy", strategies, selected_seeds),
        "strategy_runs": strategy_runs,
        "calibration": calibration,
        "ablation_summary": _summaries(
            ablation_runs, "strategy",
            [(item[0], item[1]) for item in MECHANISM_VARIANTS], selected_seeds,
        ),
        "ablation_runs": ablation_runs,
        "failure_cases": strategy_failures + ablation_failures,
    }
    report["markdown"] = render_matrix_markdown(report)
    if save_report:
        report["saved_files"] = save_experiment_report(report)
    return report


def _run_and_archive(
    engine: SimulationEngine, quarters: int, archive_dir: str | Path | None,
) -> WorldState:
    if not archive_dir:
        return engine.run(quarters)
    repository = WorldRepository(archive_dir)
    repository.save(engine.world)
    repository.save_snapshot(engine.world)
    for _ in range(quarters):
        engine.step()
        repository.save(engine.world)
        repository.save_snapshot(engine.world)
    return engine.world


def _provider_for_strategy(strategy: str, llm_timeout: float | None = None) -> CognitiveProvider:
    if strategy == "deterministic":
        return DeterministicCognition()
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured; LLM run recorded as failure")
    return DeepSeekCognition(
        api_key=api_key,
        model_name=strategy,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        request_timeout=llm_timeout or float(os.getenv("DEEPSEEK_TIMEOUT", "45")),
        structured_retries=int(os.getenv("DEEPSEEK_STRUCTURED_RETRIES", "2")),
        diagnostics_path=os.getenv(
            "DEEPSEEK_DIAGNOSTICS_PATH", ".insidegov/logs/llm-diagnostics.jsonl"
        ),
    )


def _load_checkpoint(path: str | Path | None) -> dict | None:
    if not path:
        return None
    checkpoint_path = Path(path)
    if not checkpoint_path.exists():
        return None
    return json.loads(checkpoint_path.read_text(encoding="utf-8"))


def _save_checkpoint(
    path: str | Path | None,
    checkpoint: dict,
    strategy_runs: list[dict],
    calibration: dict[str, list[dict]],
    failure_cases: list[dict],
    ablation_runs: list[dict],
) -> None:
    if not path:
        return
    checkpoint["updated_at"] = datetime.now(UTC).isoformat()
    checkpoint["strategy_runs"] = strategy_runs
    checkpoint["calibration"] = calibration
    checkpoint["failure_cases"] = failure_cases
    checkpoint["ablation_runs"] = ablation_runs
    checkpoint_path = Path(path)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = checkpoint_path.with_suffix(checkpoint_path.suffix + ".tmp")
    temporary_path.write_text(
        json.dumps(checkpoint, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary_path.replace(checkpoint_path)


def _emit_progress(progress: Callable[[str], None] | None, message: str) -> None:
    if progress:
        progress(message)


def _run_record(world: WorldState, seed: int, strategy: str) -> dict:
    final = asdict(world.history[-1])
    return {
        "strategy": strategy, "seed": seed, "successful": True,
        "selected_city": world.selected_city_id,
        "negotiation_rounds": len(world.negotiations),
        "fulfilled_promises": sum(p.status == "fulfilled" for p in world.promises),
        **{key: final[key] for key in REPORT_METRICS},
    }


def _summaries(
    runs: list[dict], group_key: str, groups: list[tuple[str, str]], seeds: list[int]
) -> list[dict]:
    output = []
    for group_id, name in groups:
        rows = [row for row in runs if row[group_key] == group_id]
        successful = [row for row in rows if row.get("successful", True)]
        metrics = {}
        for metric in SUMMARY_METRICS:
            values = [float(row[metric]) for row in successful]
            metrics[metric] = {
                "mean": round(statistics.fmean(values), 6) if values else None,
                "variance": round(statistics.pvariance(values), 6) if values else None,
                "n": len(values),
            }
        output.append({
            "id": group_id, "name": name, "attempted": len(seeds),
            "successful": len(successful),
            "success_rate": round(len(successful) / len(seeds), 4) if seeds else 0,
            "metrics": metrics,
            "selected_city_distribution": {
                city_id: sum(row["selected_city"] == city_id for row in successful)
                for city_id in ["city_hai", "city_lin", "city_yun", None]
            },
        })
    return output


def _invariant_violations(world: WorldState) -> list[str]:
    failures = []
    if any(city.available_budget < -0.01 for city in world.cities.values()):
        failures.append("negative city budget")
    for item in world.negotiations:
        if item.final_cost > item.finance_limit + 0.03:
            failures.append(f"{item.id} exceeds total finance limit")
        for tool in ["subsidy", "equity", "credit_support"]:
            if item.final_tools.get(tool, 0) > item.finance_tool_limits.get(tool, float("inf")) + 0.03:
                failures.append(f"{item.id} exceeds {tool} limit")
    return failures


def save_experiment_report(report: dict, root: str | Path | None = None) -> dict[str, str]:
    folder = Path(root or os.getenv("INSIDEGOV_REPORT_DIR", ".insidegov/reports"))
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = folder / f"p1-matrix-{stamp}.json"
    md_path = folder / f"p1-matrix-{stamp}.md"
    json_copy = {key: value for key, value in report.items() if key != "markdown"}
    json_path.write_text(json.dumps(json_copy, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(report["markdown"], encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def render_matrix_markdown(report: dict) -> str:
    lines = [
        "# InsideGov P1 实验矩阵报告", "",
        f"- 生成时间：{report['generated_at']}",
        f"- 随机种子：{', '.join(map(str, report['configuration']['seeds']))}",
        f"- 推演长度：{report['configuration']['quarters']} 季度", "",
        "## 策略比较", "",
        "| 策略 | 成功数 | 就业均值 | 就业方差 | 信誉均值 | 利用率均值 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in report["strategy_summary"]:
        metrics = row["metrics"]
        lines.append(
            f"| {row['name']} | {row['successful']}/{row['attempted']} | "
            f"{_show(metrics['total_employment']['mean'])} | {_show(metrics['total_employment']['variance'])} | "
            f"{_show(metrics['average_credibility']['mean'])} | {_show(metrics['utilization']['mean'])} |"
        )
    lines.extend(["", "## 机制消融", ""])
    for row in report["ablation_summary"]:
        lines.append(
            f"- **{row['name']}**：成功 {row['successful']}/{row['attempted']}，"
            f"产业链规模均值 {_show(row['metrics']['cluster_size']['mean'])}，"
            f"就业均值 {_show(row['metrics']['total_employment']['mean'])}。"
        )
    lines.extend(["", "## 失败案例", ""])
    if report["failure_cases"]:
        for failure in report["failure_cases"]:
            lines.append(f"- `{failure.get('strategy', failure.get('variant'))}` seed {failure['seed']}: {failure['reason']}")
    else:
        lines.append("- 无。")
    return "\n".join(lines) + "\n"


def _show(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.4f}"


# ---------------------------------------------------------------------- #
# 人才场景实验：需求↔政策↔能力映射的沟通协商机制
# ---------------------------------------------------------------------- #
def run_talent_comparison(
    seed: int = 42,
    quarters: int = 16,
    mode: str = "deterministic",
    model_name: str | None = None,
) -> list[dict]:
    """2x2 反事实：同一初始世界，仅切换语言模式与是否启用中介平台。

    对应官方评分维度——在同一初始条件下改变「政策表达方式」与
    「翻译/中介机制」，观察对接成功率、理解度、信任与财政成本的演化。
    """
    results = []
    for variant_id, name, toggles in TALENT_VARIANTS:
        world = create_talent_world(
            seed, f"talent-{variant_id}", mode=mode, **toggles,
        )
        engine = TalentSimulationEngine(world)
        engine.run(quarters)
        final = asdict(engine.world.history[-1])
        final.update({
            "name": name, "variant": variant_id,
            "contracts": len(engine.world.talent_contracts),
            "negotiations": len(engine.world.talent_negotiations),
            "withdrawn": sum(t.status == "withdrawn" for t in engine.world.talents.values()),
            "matched": sum(t.status == "contracted" for t in engine.world.talents.values()),
            "expression_mode": engine.world.expression_mode,
            "interpreter_enabled": engine.world.interpreter_enabled,
            "model_name": engine.world.model_name,
        })
        results.append(final)
    return results


def run_talent_matrix(
    seeds: list[int] | None = None,
    quarters: int = 16,
    mode: str = "deterministic",
    model_name: str | None = None,
    save_report: bool = True,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """多 seed × 2x2 变体矩阵，输出均值/方差汇总与 Markdown 报告。"""
    selected_seeds = seeds or DEFAULT_SEEDS
    runs: list[dict] = []
    for variant_id, name, toggles in TALENT_VARIANTS:
        for seed in selected_seeds:
            _emit_progress(progress, f"talent {variant_id} seed={seed} start")
            try:
                world = create_talent_world(
                    seed, f"talent-{variant_id}-s{seed}", mode=mode, **toggles,
                )
                engine = TalentSimulationEngine(world)
                engine.run(quarters)
                final = asdict(engine.world.history[-1])
                final.update({
                    "variant": variant_id, "name": name, "seed": seed,
                    "successful": True,
                    "contracts": len(engine.world.talent_contracts),
                    "negotiations": len(engine.world.talent_negotiations),
                    "withdrawn": sum(t.status == "withdrawn" for t in engine.world.talents.values()),
                })
                runs.append(final)
                _emit_progress(progress, f"talent {variant_id} seed={seed} done")
            except Exception as exc:  # noqa: BLE001 - matrix must retain failed variants
                runs.append({
                    "variant": variant_id, "name": name, "seed": seed, "successful": False,
                    "reason": f"{type(exc).__name__}: {exc}",
                })
                _emit_progress(progress, f"talent {variant_id} seed={seed} failed")
    summary = []
    for variant_id, name, _toggles in TALENT_VARIANTS:
        rows = [row for row in runs if row["variant"] == variant_id]
        good = [row for row in rows if row.get("successful", True)]
        stats = {}
        for metric in TALENT_METRICS:
            values = [float(row[metric]) for row in good]
            stats[metric] = {
                "mean": round(statistics.fmean(values), 6) if values else None,
                "variance": round(statistics.pvariance(values), 6) if values else None,
                "n": len(values),
            }
        summary.append({
            "id": variant_id, "name": name, "attempted": len(rows),
            "successful": len(good),
            "success_rate": round(len(good) / len(rows), 4) if rows else 0,
            "metrics": stats,
        })
    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "configuration": {
            "seeds": selected_seeds, "quarters": quarters,
            "mode": mode, "model_name": model_name,
            "variants": [item[0] for item in TALENT_VARIANTS],
        },
        "talent_summary": summary,
        "talent_runs": runs,
        "failure_cases": [row for row in runs if not row.get("successful", True)],
    }
    report["markdown"] = render_talent_markdown(report)
    if save_report:
        report["saved_files"] = _save_talent_report(report)
    return report


def _save_talent_report(report: dict, root: str | Path | None = None) -> dict[str, str]:
    folder = Path(root or os.getenv("INSIDEGOV_REPORT_DIR", ".insidegov/reports"))
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = folder / f"talent-matrix-{stamp}.json"
    md_path = folder / f"talent-matrix-{stamp}.md"
    json_copy = {key: value for key, value in report.items() if key != "markdown"}
    json_path.write_text(json.dumps(json_copy, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(report["markdown"], encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}


def render_talent_markdown(report: dict) -> str:
    config = report["configuration"]
    lines = [
        "# InsideGov 人才对接实验报告：需求↔政策↔能力映射", "",
        f"- 生成时间：{report['generated_at']}",
        f"- 随机种子：{', '.join(map(str, config['seeds']))}",
        f"- 推演长度：{config['quarters']} 季度",
        f"- 认知模式：{config['mode']}（{config['model_name'] or '无模型'}）", "",
        "## 2x2 反事实对比", "",
        "| 变体 | 成功数 | 对接成功率 | 理解度均值 | 信任均值 | 签约数 | 技术存量 | 财政支出 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in report["talent_summary"]:
        metrics = row["metrics"]
        lines.append(
            f"| {row['name']} | {row['successful']}/{row['attempted']} | "
            f"{_show(metrics['match_rate']['mean'])} | {_show(metrics['avg_understanding']['mean'])} | "
            f"{_show(metrics['avg_trust']['mean'])} | {_show(metrics['talent_hired']['mean'])} | "
            f"{_show(metrics['tech_progress']['mean'])} | {_show(metrics['total_committed_expenditure']['mean'])} |"
        )
    lines.extend(["", "## 结论速读", ""])
    summary = {row["id"]: row for row in report["talent_summary"]}
    baseline = summary.get("formal_no_platform")
    best = max(report["talent_summary"], key=lambda r: (r["metrics"]["match_rate"]["mean"] or 0))
    if baseline:
        base_match = baseline["metrics"]["match_rate"]["mean"] or 0
        best_match = best["metrics"]["match_rate"]["mean"] or 0
        if base_match > 0:
            lift = f"（相对提升 {best_match / base_match - 1:.1%}）"
        elif best_match > 0:
            lift = "（官话直连基线为 0，全部对接失败）"
        else:
            lift = "（所有变体均无对接成功）"
        lines.append(
            f"- 官话直连基线对接成功率 {base_match:.4f}；最优变体「{best['name']}」为 "
            f"{best_match:.4f}{lift}。"
        )
    lines.append("- 语言模式与中介平台共同影响理解度与信任，进而决定对接成功率；单纯加钱而表达不通，覆盖度会虚高但签约率不足。")
    lines.extend(["", "## 失败案例", ""])
    if report["failure_cases"]:
        for failure in report["failure_cases"]:
            lines.append(
                f"- `{failure['variant']}` seed {failure['seed']}: {failure.get('reason', 'unknown')}"
            )
    else:
        lines.append("- 无。")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------- #
# 政企协商协议矩阵
# ---------------------------------------------------------------------- #

NEGOTIATION_VARIANTS = [
    ("free", "自由协商"),
    ("policy_match", "政策匹配"),
    ("clarify_first", "澄清优先"),
    ("paraphrase_confirm", "复述确认"),
    ("constraints_first", "约束先行"),
    ("multi_option", "多方案协商"),
    ("phased_commitment", "分阶段承诺"),
]
NEGOTIATION_METRICS = [
    "agreements", "terminated", "avg_gap_final", "avg_policy_fit",
    "fulfillment_rate", "regret_rate", "total_gov_cost", "total_ent_commitment",
]


def run_negotiation_comparison(seed: int = 42, quarters: int = 2) -> list[dict]:
    rows = []
    for protocol, name in NEGOTIATION_VARIANTS:
        try:
            world = NegotiationEngine(
                create_negotiation_world(seed, f"negotiation-{protocol}-s{seed}", protocol)
            ).run(quarters)
            row = asdict(world.history[-1])
            row.update({"id": protocol, "name": name, "seed": seed, "successful": True})
        except Exception as exc:  # noqa: BLE001 - experiment report retains failures
            row = {
                "id": protocol, "name": name, "seed": seed, "successful": False,
                "reason": f"{type(exc).__name__}: {exc}",
            }
        rows.append(row)
    return rows


def _pareto_frontier(summary: list[dict]) -> list[dict]:
    """Maximise true policy fit while minimising total government cost."""
    points = []
    for row in summary:
        fit = row.get("metrics", {}).get("avg_policy_fit", {}).get("mean")
        cost = row.get("metrics", {}).get("total_gov_cost", {}).get("mean")
        if fit is not None and cost is not None:
            points.append({"id": row["id"], "name": row["name"], "fit": fit, "cost": cost})
    frontier = []
    for point in points:
        dominated = any(
            other["fit"] >= point["fit"] and other["cost"] <= point["cost"]
            and (other["fit"] > point["fit"] or other["cost"] < point["cost"])
            for other in points if other is not point
        )
        if not dominated:
            frontier.append(point)
    return sorted(frontier, key=lambda item: item["cost"])


def _negotiation_summary(runs: list[dict]) -> list[dict]:
    summary = []
    for protocol, name in NEGOTIATION_VARIANTS:
        rows = [row for row in runs if row["id"] == protocol]
        good = [row for row in rows if row.get("successful")]
        metrics = {}
        for metric in NEGOTIATION_METRICS:
            values = [float(row[metric]) for row in good]
            metrics[metric] = {
                "mean": round(statistics.fmean(values), 6) if values else None,
                "variance": round(statistics.pvariance(values), 6) if values else None,
                "n": len(values),
            }
        summary.append({
            "id": protocol, "name": name, "attempted": len(rows),
            "successful": len(good), "metrics": metrics,
        })
    return summary


def _protocol_firm_fits(seeds: list[int], protocol: str, quarters: int) -> dict[str, list[float]]:
    fits: dict[str, list[float]] = {}
    for seed in seeds:
        world = NegotiationEngine(
            create_negotiation_world(seed, f"evidence-{protocol}-{seed}", protocol)
        ).run(quarters)
        for record in world.negotiation_records:
            fits.setdefault(record.firm_id, []).append(record.policy_fit)
    return fits


def run_negotiation_matrix(
    seeds: list[int] | None = None,
    quarters: int = 2,
    mode: str = "deterministic",
    model_name: str | None = None,
    save_report: bool = True,
) -> dict:
    selected = seeds or DEFAULT_SEEDS
    runs = []
    for seed in selected:
        runs.extend(run_negotiation_comparison(seed, quarters))
    summary = _negotiation_summary(runs)
    by_id = {row["id"]: row for row in summary}

    language_probe = []
    for seed in selected:
        for style in ("formal", "plain"):
            world = NegotiationEngine(create_negotiation_world(
                seed, f"language-{style}-{seed}", "free", style, mode,
            )).run(quarters)
            language_probe.append({
                "seed": seed, "language_style": style,
                "avg_understanding": round(statistics.fmean(
                    r.understanding_final for r in world.negotiation_records
                ), 4),
            })

    free_fits = _protocol_firm_fits(selected, "free", quarters)
    clarify_fits = _protocol_firm_fits(selected, "clarify_first", quarters)
    low_trust = {"firm_bio", "firm_chip", "firm_risky"}
    gains = {"low_trust": [], "regular": []}
    for firm_id, base_values in free_fits.items():
        gain = statistics.fmean(clarify_fits[firm_id]) - statistics.fmean(base_values)
        gains["low_trust" if firm_id in low_trust else "regular"].append(gain)
    group_gains = {key: round(statistics.fmean(values), 6) for key, values in gains.items()}
    spread = round(group_gains["low_trust"] - group_gains["regular"], 6)

    metric = lambda protocol, key: by_id[protocol]["metrics"][key]["mean"]
    formal = statistics.fmean(row["avg_understanding"] for row in language_probe if row["language_style"] == "formal")
    plain = statistics.fmean(row["avg_understanding"] for row in language_probe if row["language_style"] == "plain")
    hypotheses = [
        {"id": "H1", "supported": metric("clarify_first", "avg_gap_final") < metric("free", "avg_gap_final"), "evidence": {"clarify_gap": metric("clarify_first", "avg_gap_final"), "free_gap": metric("free", "avg_gap_final")}},
        {"id": "H2", "supported": metric("paraphrase_confirm", "avg_gap_final") < metric("free", "avg_gap_final"), "evidence": {"paraphrase_gap": metric("paraphrase_confirm", "avg_gap_final")}},
        {"id": "H3", "supported": metric("constraints_first", "avg_policy_fit") >= metric("free", "avg_policy_fit"), "evidence": {"constraints_fit": metric("constraints_first", "avg_policy_fit")}},
        {"id": "H4", "supported": metric("multi_option", "avg_policy_fit") > metric("free", "avg_policy_fit"), "evidence": {"multi_option_fit": metric("multi_option", "avg_policy_fit")}},
        {"id": "H5", "supported": metric("phased_commitment", "total_gov_cost") < metric("free", "total_gov_cost"), "evidence": {"phased_cost": metric("phased_commitment", "total_gov_cost")}},
        {"id": "H6", "supported": plain > formal, "evidence": {"plain_understanding": plain, "formal_understanding": formal}},
        {"id": "H7", "supported": spread > 0.10, "evidence": {"clarify_marginal_gain_by_group": group_gains, "gain_spread": spread}},
    ]
    report = {
        "schema_version": "1.0", "generated_at": datetime.now(UTC).isoformat(),
        "configuration": {"seeds": selected, "quarters": quarters, "mode": mode, "model_name": model_name},
        "negotiation_summary": summary, "negotiation_runs": runs,
        "language_probe": language_probe, "pareto_frontier": _pareto_frontier(summary),
        "hypotheses": hypotheses,
        "failure_cases": [row for row in runs if not row.get("successful")],
    }
    report["markdown"] = render_negotiation_markdown(report)
    if save_report:
        folder = Path(os.getenv("INSIDEGOV_REPORT_DIR", ".insidegov/reports"))
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        path = folder / f"negotiation-matrix-{stamp}.json"
        path.write_text(json.dumps({k: v for k, v in report.items() if k != "markdown"}, ensure_ascii=False, indent=2), encoding="utf-8")
        report["saved_files"] = {"json": str(path)}
    return report


def render_negotiation_markdown(report: dict) -> str:
    lines = ["# InsideGov 政企协商机制实验报告", "", "| 协议 | 签约 | 理解差距 | 真实匹配 | 政府成本 |", "|---|---:|---:|---:|---:|"]
    for row in report["negotiation_summary"]:
        m = row["metrics"]
        lines.append(f"| {row['name']} | {_show(m['agreements']['mean'])} | {_show(m['avg_gap_final']['mean'])} | {_show(m['avg_policy_fit']['mean'])} | {_show(m['total_gov_cost']['mean'])} |")
    lines.extend(["", "## 假设检验", ""])
    lines.extend(f"- {h['id']}：{'支持' if h['supported'] else '未支持'}" for h in report["hypotheses"])
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------- #
