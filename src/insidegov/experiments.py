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
from .scenarios import create_full_lifecycle_world

DEFAULT_SEEDS = [11, 23, 42, 57, 89]
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
    provider_factory: Callable[[str], CognitiveProvider] | None = None,
    save_report: bool = True,
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
    factory = provider_factory or _provider_for_strategy
    provider_cache: dict[str, CognitiveProvider] = {}

    def provider(strategy_id: str) -> CognitiveProvider:
        if strategy_id not in provider_cache:
            provider_cache[strategy_id] = factory(strategy_id)
        return provider_cache[strategy_id]

    strategy_runs: list[dict] = []
    strategy_failures: list[dict] = []
    calibration: dict[str, list[dict]] = {}

    for strategy_id, strategy_name in strategies:
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
                strategy_failures.append({
                    "strategy": strategy_id, "seed": "calibration",
                    "stage": f"calibration:{calibration_case['id']}",
                    "reason": calibration_case.get("failure_reason") or calibration_case["observed"],
                    "last_events": [],
                })
        for seed in selected_seeds:
            try:
                cognition = provider(strategy_id)
                world = create_full_lifecycle_world(seed, f"{strategy_name} / seed {seed}")
                world.policy_mode = "deterministic" if strategy_id == "deterministic" else "llm"
                world.model_name = None if strategy_id == "deterministic" else strategy_id
                engine = SimulationEngine(world, cognition=cognition)
                engine.run(quarters)
                record = _run_record(engine.world, seed, strategy_id)
                fallbacks = [event for event in engine.world.events if event.kind == "model_fallback"]
                violations = _invariant_violations(engine.world)
                if fallbacks or violations:
                    strategy_failures.append({
                        "strategy": strategy_id, "seed": seed, "stage": "simulation",
                        "reason": "; ".join(
                            [f"{len(fallbacks)} cognitive fallbacks"] + violations
                        ),
                        "last_events": [event.title for event in engine.world.events[-5:]],
                    })
                    record["successful"] = False
                strategy_runs.append(record)
            except Exception as exc:  # noqa: BLE001 - failure case is report output
                strategy_failures.append({
                    "strategy": strategy_id, "seed": seed, "stage": "initialization_or_run",
                    "reason": f"{type(exc).__name__}: {exc}", "last_events": [],
                })

    ablation_runs: list[dict] = []
    ablation_failures: list[dict] = []
    for variant_id, name, toggles in MECHANISM_VARIANTS:
        for seed in selected_seeds:
            try:
                world = create_full_lifecycle_world(seed, f"{name} / seed {seed}")
                world.mechanisms.update(toggles)
                engine = SimulationEngine(world, cognition=DeterministicCognition())
                engine.run(quarters)
                ablation_runs.append(_run_record(engine.world, seed, variant_id))
            except Exception as exc:  # noqa: BLE001 - failure case is report output
                ablation_failures.append({
                    "variant": variant_id, "seed": seed,
                    "reason": f"{type(exc).__name__}: {exc}",
                })

    report = {
        "schema_version": "1.0",
        "generated_at": datetime.now(UTC).isoformat(),
        "configuration": {
            "seeds": selected_seeds, "quarters": quarters,
            "strategies": [item[0] for item in strategies],
            "ablations": [item[0] for item in MECHANISM_VARIANTS],
        },
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


def _provider_for_strategy(strategy: str) -> CognitiveProvider:
    if strategy == "deterministic":
        return DeterministicCognition()
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured; LLM run recorded as failure")
    return DeepSeekCognition(
        api_key=api_key,
        model_name=strategy,
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
    )


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
        for metric in REPORT_METRICS:
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
