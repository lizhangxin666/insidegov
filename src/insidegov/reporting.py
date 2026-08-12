"""Experiment report discovery and auditable run drill-down."""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path

from .models import WorldState
from .serde import world_from_dict

SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class ExperimentReportRepository:
    def __init__(
        self,
        report_root: str | Path | None = None,
        matrix_root: str | Path | None = None,
        bundled_artifact: str | Path | None = None,
        bundled_runs: str | Path | None = None,
    ) -> None:
        self.report_root = Path(
            report_root or os.getenv("INSIDEGOV_REPORT_DIR", ".insidegov/reports")
        )
        self.matrix_root = Path(
            matrix_root or os.getenv("INSIDEGOV_MATRIX_WORLD_DIR", ".insidegov/matrix-worlds")
        )
        self.bundled_artifact = Path(
            bundled_artifact or "docs/reports/p1-visual-report/artifact.json"
        )
        self.bundled_runs = Path(
            bundled_runs or "docs/reports/p1-visual-report/runs.json"
        )

    def list(self) -> list[dict]:
        items: list[dict] = []
        if self.report_root.exists():
            for path in sorted(
                self.report_root.glob("*.json"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            ):
                try:
                    report = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                items.append(self._summary(path.stem, report, "local_matrix"))
        if self.bundled_runs.exists():
            report = json.loads(self.bundled_runs.read_text(encoding="utf-8"))
            items.append(self._summary("p1-public-runs", report, "bundled_public_runs"))
        if self.bundled_artifact.exists():
            artifact = json.loads(self.bundled_artifact.read_text(encoding="utf-8"))
            items.append({
                "id": "p1-visual-bundled",
                "title": artifact.get("manifest", {}).get(
                    "title", "P1 多策略与机制消融可视化报告"
                ),
                "kind": "p1_visual",
                "source": "bundled_release_artifact",
                "generated_at": artifact.get("manifest", {}).get("generatedAt"),
                "strategy_runs": 0,
                "ablation_runs": 0,
                "failures": 0,
                "drilldown_available": False,
            })
        return items

    def load(self, report_id: str) -> dict | None:
        if report_id == "p1-public-runs" and self.bundled_runs.exists():
            report = json.loads(self.bundled_runs.read_text(encoding="utf-8"))
            return self._enrich(report_id, report, "bundled_public_runs")
        if report_id == "p1-visual-bundled" and self.bundled_artifact.exists():
            return self._load_bundled()
        if not SAFE_ID.fullmatch(report_id):
            return None
        target = self.report_root / f"{report_id}.json"
        if not target.exists():
            return None
        report = json.loads(target.read_text(encoding="utf-8"))
        return self._enrich(report_id, report, "local_matrix")

    def _enrich(self, report_id: str, report: dict, source: str) -> dict:
        enriched = copy.deepcopy(report)
        for group, prefix in (
            ("strategy_runs", "matrix"),
            ("ablation_runs", "matrix-ablation"),
        ):
            for run in enriched.get(group, []):
                world_id = run.get("world_id") or (
                    f"{prefix}-{run.get('strategy')}-seed-{run.get('seed')}"
                )
                run["world_id"] = world_id
                run["world_available"] = (self.matrix_root / f"{world_id}.json").exists()
        enriched["report_id"] = report_id
        enriched["report_summary"] = self._summary(report_id, enriched, source)
        return enriched

    def load_world(self, world_id: str) -> WorldState | None:
        if not SAFE_ID.fullmatch(world_id):
            return None
        target = self.matrix_root / f"{world_id}.json"
        if not target.exists():
            return None
        return world_from_dict(json.loads(target.read_text(encoding="utf-8")))

    @staticmethod
    def _summary(report_id: str, report: dict, source: str) -> dict:
        if "strategy_summary" in report:
            kind = "p1_matrix"
            title = "P1 多策略、随机种子与机制消融"
        elif "negotiation_summary" in report:
            kind = "negotiation_matrix"
            title = "七种政企协商协议实验"
        elif "talent_summary" in report:
            kind = "talent_matrix"
            title = "人才对接 2×2 实验"
        else:
            kind = "experiment"
            title = report_id
        return {
            "id": report_id,
            "title": title,
            "kind": kind,
            "source": source,
            "generated_at": report.get("generated_at") or report.get("updated_at"),
            "strategy_runs": len(report.get("strategy_runs", [])),
            "ablation_runs": len(report.get("ablation_runs", [])),
            "failures": len(report.get("failure_cases", [])),
            "drilldown_available": bool(
                report.get("strategy_runs") or report.get("ablation_runs")
            ),
        }

    def _load_bundled(self) -> dict:
        artifact = json.loads(self.bundled_artifact.read_text(encoding="utf-8"))
        datasets = artifact.get("snapshot", {}).get("datasets", {})
        return {
            "report_id": "p1-visual-bundled",
            "schema_version": "visual-artifact-1",
            "generated_at": artifact.get("manifest", {}).get("generatedAt"),
            "configuration": {"source": "bundled_release_artifact"},
            "strategy_summary": datasets.get("strategy_comparison", []),
            "ablation_summary": datasets.get("mechanism_effects", []),
            "strategy_runs": [],
            "ablation_runs": [],
            "failure_cases": [],
            "llm_quality": datasets.get("llm_quality", []),
            "headline": datasets.get("headline", []),
            "report_summary": {
                "id": "p1-visual-bundled",
                "title": artifact.get("manifest", {}).get("title"),
                "kind": "p1_visual",
                "source": "bundled_release_artifact",
                "drilldown_available": False,
            },
        }
