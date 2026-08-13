"""Durable public-experience jobs and human-readable progress events."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from copy import deepcopy
from dataclasses import asdict
from pathlib import Path
from typing import Any

TERMINAL_STATUSES = {"completed", "failed", "canceled", "partial"}
RUNNING_STATUSES = {"queued", "running", "waiting_user", "canceling"}

SCENE_META = {
    "coordination": ("重大项目会商预演", ["准备会场", "部门形成判断", "内部协调", "企业回应", "形成结果"]),
    "diligence": ("项目真实性判断", ["读取企业主张", "选择核验方向", "获得证据", "形成风险判断", "生成说明"]),
    "dynamic_competition": ("产业救助压力测试", ["建立产业世界", "观察扩张", "注入需求冲击", "处理救助与退出", "跨期结算"]),
    "conversation": ("协商机制压力测试", ["理解新情况", "项目核验", "政企协商", "规则结算", "整理证据链"]),
    "story_turn": ("第一人称组织博弈", ["读取你的行动", "其他组织回应", "规则检查", "世界结算", "生成本回合故事"]),
}


class PublicJobRepository:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.getenv("INSIDEGOV_PUBLIC_JOB_DB", ".insidegov/public-jobs.sqlite3"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS public_jobs (
                    id TEXT PRIMARY KEY,
                    scene TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage_index INTEGER NOT NULL DEFAULT 0,
                    stage_label TEXT NOT NULL,
                    message TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    result_json TEXT,
                    checkpoint_json TEXT,
                    error TEXT,
                    pid INTEGER,
                    model_name TEXT NOT NULL,
                    attempt INTEGER NOT NULL DEFAULT 1,
                    parent_job_id TEXT,
                    cancellation_requested INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    started_at REAL,
                    updated_at REAL NOT NULL,
                    finished_at REAL,
                    heartbeat_at REAL
                );
                CREATE TABLE IF NOT EXISTS public_job_events (
                    job_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    stage_index INTEGER NOT NULL,
                    actor TEXT,
                    title TEXT NOT NULL,
                    detail TEXT NOT NULL,
                    tone TEXT NOT NULL DEFAULT 'neutral',
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at REAL NOT NULL,
                    PRIMARY KEY (job_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_public_jobs_updated
                    ON public_jobs(updated_at DESC);
            """)

    def create(
        self, scene: str, config: dict[str, Any], model_name: str,
        *, parent_job_id: str | None = None, attempt: int = 1,
        checkpoint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if scene not in SCENE_META:
            raise ValueError(f"unknown public scene: {scene}")
        now = time.time()
        job_id = f"public-{uuid.uuid4().hex[:12]}"
        title, stages = SCENE_META[scene]
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO public_jobs
                (id, scene, title, status, stage_index, stage_label, message,
                 config_json, checkpoint_json, model_name, attempt, parent_job_id,
                 created_at, updated_at, heartbeat_at)
                VALUES (?, ?, ?, 'queued', 0, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    job_id, scene, title, stages[0], "任务已经进入队列，正在准备独立世界。",
                    json.dumps(config, ensure_ascii=False),
                    json.dumps(checkpoint, ensure_ascii=False) if checkpoint else None,
                    model_name, attempt, parent_job_id, now, now, now,
                ),
            )
        self.event(job_id, "job.queued", 0, "任务已创建", "你可以离开此页面，推演会在后台继续。")
        return self.get(job_id)

    def get(self, job_id: str, *, include_result: bool = True) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM public_jobs WHERE id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            event_count = connection.execute(
                "SELECT COUNT(*) FROM public_job_events WHERE job_id = ?", (job_id,)
            ).fetchone()[0]
        payload = dict(row)
        for key in ("config_json", "result_json", "checkpoint_json"):
            payload[key.removesuffix("_json")] = json.loads(payload.pop(key)) if payload[key] else None
        if not include_result:
            payload.pop("result", None)
        payload["cancellation_requested"] = bool(payload["cancellation_requested"])
        payload["event_count"] = event_count
        payload["stages"] = SCENE_META[payload["scene"]][1]
        payload["elapsed_seconds"] = round(
            (payload["finished_at"] or time.time()) - (payload["started_at"] or payload["created_at"]), 1
        )
        return payload

    def list(self, limit: int = 30) -> list[dict[str, Any]]:
        with self._connect() as connection:
            ids = [row[0] for row in connection.execute(
                "SELECT id FROM public_jobs ORDER BY updated_at DESC LIMIT ?", (limit,)
            )]
        return [self.get(job_id, include_result=False) for job_id in ids]

    def update(self, job_id: str, **changes: Any) -> None:
        if not changes:
            return
        serialized = {}
        for key, value in changes.items():
            serialized[f"{key}_json" if key in {"result", "checkpoint", "config"} else key] = (
                json.dumps(value, ensure_ascii=False) if key in {"result", "checkpoint", "config"} else value
            )
        serialized["updated_at"] = time.time()
        columns = ", ".join(f"{key} = ?" for key in serialized)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE public_jobs SET {columns} WHERE id = ?",
                (*serialized.values(), job_id),
            )

    def event(
        self, job_id: str, event_type: str, stage_index: int, title: str, detail: str,
        *, actor: str | None = None, tone: str = "neutral", payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        with self._lock, self._connect() as connection:
            sequence = connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM public_job_events WHERE job_id = ?",
                (job_id,),
            ).fetchone()[0]
            created_at = time.time()
            connection.execute(
                """INSERT INTO public_job_events
                (job_id, sequence, event_type, stage_index, actor, title, detail, tone, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (job_id, sequence, event_type, stage_index, actor, title, detail, tone,
                 json.dumps(payload or {}, ensure_ascii=False), created_at),
            )
        return {
            "job_id": job_id, "sequence": sequence, "event_type": event_type,
            "stage_index": stage_index, "actor": actor, "title": title,
            "detail": detail, "tone": tone, "payload": payload or {}, "created_at": created_at,
        }

    def events(self, job_id: str, after: int = 0) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM public_job_events WHERE job_id = ? AND sequence > ? ORDER BY sequence",
                (job_id, after),
            ).fetchall()
        results = []
        for row in rows:
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            results.append(item)
        return results

    def request_cancel(self, job_id: str) -> dict[str, Any]:
        job = self.get(job_id)
        if job["status"] in TERMINAL_STATUSES:
            return job
        self.update(job_id, cancellation_requested=1, status="canceling", message="正在安全停止，已完成内容会保留。")
        if job.get("pid"):
            try:
                os.kill(int(job["pid"]), signal.SIGTERM)
            except ProcessLookupError:
                pass
        self.event(job_id, "job.canceling", job["stage_index"], "正在安全停止", "已经完成的行动和世界检查点不会被删除。", tone="warning")
        return self.get(job_id)


def launch_public_job(job_repository: PublicJobRepository, job_id: str) -> None:
    process = subprocess.Popen(
        [sys.executable, "-m", "insidegov.public_worker", "--job-id", job_id,
         "--database", str(job_repository.path)],
        cwd=Path.cwd(),
        start_new_session=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    job_repository.update(job_id, pid=process.pid)


def redact_world(world) -> dict[str, Any]:
    result = deepcopy(world.to_dict())
    if result.get("project_risk_profiles"):
        result["project_risk_profiles"] = {
            firm_id: {"redacted": True, "fields": sorted(profile)}
            for firm_id, profile in result["project_risk_profiles"].items()
        }
    for agent in result.get("agents", {}).values():
        agent["private_facts"] = {"redacted": True, "fields": sorted(agent.get("private_facts", {}))}
    for audit in result.get("action_audits", []):
        audit["private_context_used"] = {
            "redacted": True,
            "fields_used": sorted(audit.get("private_context_used", {})),
        }
    return result


def case_payload(world, case) -> dict[str, Any]:
    payload = asdict(case)
    payload["firm_name"] = world.firms[case.firm_id].name
    return payload
