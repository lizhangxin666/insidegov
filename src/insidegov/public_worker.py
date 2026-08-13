"""Detached worker for durable public InsideGov experiences."""

from __future__ import annotations

import argparse
import os
import signal
import sqlite3
import threading
import time
from typing import Any

from .due_diligence import DueDiligenceEngine, due_diligence_metrics
from .dynamic_competition import run_dynamic_competition_experiment
from .engine import SimulationEngine
from .experience import (
    StorySessionRepository,
    run_conversation_experience,
    take_story_turn,
)
from .public_jobs import PublicJobRepository, case_payload, redact_world
from .repository import WorldRepository
from .scenarios import create_full_lifecycle_world, create_negotiation_world

JOB_REPOSITORY: PublicJobRepository | None = None
CURRENT_JOB_ID = ""
STOP_HEARTBEAT = threading.Event()


def _stage(index: int, message: str) -> None:
    assert JOB_REPOSITORY is not None
    job = JOB_REPOSITORY.get(CURRENT_JOB_ID)
    label = job["stages"][min(index, len(job["stages"]) - 1)]
    JOB_REPOSITORY.update(
        CURRENT_JOB_ID, status="running", stage_index=index,
        stage_label=label, message=message, heartbeat_at=time.time(),
    )
    JOB_REPOSITORY.event(CURRENT_JOB_ID, "stage.started", index, label, message)


def _event(title: str, detail: str, *, actor: str | None = None, tone: str = "neutral") -> None:
    assert JOB_REPOSITORY is not None
    job = JOB_REPOSITORY.get(CURRENT_JOB_ID)
    JOB_REPOSITORY.event(
        CURRENT_JOB_ID, "progress", job["stage_index"], title, detail,
        actor=actor, tone=tone,
    )


def _checkpoint(world_repository: WorldRepository, world, note: str) -> None:
    assert JOB_REPOSITORY is not None
    world_repository.save(world)
    path = world_repository.save_snapshot(world)
    JOB_REPOSITORY.update(
        CURRENT_JOB_ID,
        checkpoint={"world_id": world.id, "quarter": world.quarter, "snapshot": str(path), "note": note},
        heartbeat_at=time.time(),
    )


def _cancel_requested() -> bool:
    assert JOB_REPOSITORY is not None
    return bool(JOB_REPOSITORY.get(CURRENT_JOB_ID)["cancellation_requested"])


def _heartbeat() -> None:
    while not STOP_HEARTBEAT.wait(10):
        assert JOB_REPOSITORY is not None
        try:
            job = JOB_REPOSITORY.get(CURRENT_JOB_ID)
            if job["status"] not in {"queued", "running"}:
                return
            JOB_REPOSITORY.update(
                CURRENT_JOB_ID, heartbeat_at=time.time(),
                message=f"{job['stage_label']}仍在进行。Agent 正在组织信息并生成可执行行动。",
            )
        except (KeyError, sqlite3.Error):
            return


def _handle_stop(_signum, _frame) -> None:
    if JOB_REPOSITORY and CURRENT_JOB_ID:
        job = JOB_REPOSITORY.get(CURRENT_JOB_ID)
        status = "partial" if job.get("checkpoint") else "canceled"
        JOB_REPOSITORY.update(
            CURRENT_JOB_ID, status=status, finished_at=time.time(), pid=None,
            message=("任务已安全停止，已完成内容和检查点均已保留。"
                     if status == "partial" else "任务已取消，尚未形成可保存的世界节点。"),
        )
        JOB_REPOSITORY.event(
            CURRENT_JOB_ID, "job.canceled", job["stage_index"], "任务已安全停止",
            "你可以查看已有内容，或从最近检查点重新开始。", tone="warning",
        )
    raise SystemExit(0)


def _coordination(config: dict[str, Any], model_name: str, worlds: WorldRepository) -> dict:
    _stage(0, "正在建立各部门掌握不同信息的会商世界。")
    checkpoint = JOB_REPOSITORY.get(CURRENT_JOB_ID).get("checkpoint") if JOB_REPOSITORY else None
    world = worlds.load(checkpoint["world_id"]) if checkpoint and checkpoint.get("world_id") else None
    if world is not None and world.id != f"job-{CURRENT_JOB_ID}":
        parent_id = world.id
        world.id = f"job-{CURRENT_JOB_ID}"
        world.parent_id = parent_id
        world.name = "公众体验 · 重大项目会商预演（续跑）"
    if world is None:
        world = create_full_lifecycle_world(config.get("seed", 42), f"job-{CURRENT_JOB_ID}")
        world.name = "公众体验 · 重大项目会商预演"
        world.policy_mode = "llm"
        world.model_name = model_name
        world.process_mode = config.get("process_mode", "hybrid")
    engine = SimulationEngine(world)
    for turn in range(world.quarter, 3):
        if _cancel_requested():
            raise InterruptedError("canceled")
        _stage(min(turn + 1, 3), f"第 {turn + 1} 轮会商开始，各部门将独立形成判断。")
        before_actions = len(world.organization_actions)
        before_audits = len(world.action_audits)
        engine.step()
        _checkpoint(worlds, world, f"Q{world.quarter} 会商完成")
        for action in world.organization_actions[before_actions:]:
            actor = world.agents.get(action.actor_id)
            _event(
                action.action_name,
                action.blocked_reason or action.selection_rationale or action.rationale,
                actor=actor.name if actor else action.actor_id,
                tone="warning" if action.blocked_reason else "success",
            )
        _event(
            "本轮世界已结算",
            f"新增 {len(world.action_audits) - before_audits} 条 Agent 决策审计；财政与程序状态已经保存。",
            actor="InsideGov规则引擎",
        )
    _stage(4, "正在把会商过程整理成不同受众都能理解的结果。")
    return redact_world(world)


def _diligence(config: dict[str, Any], model_name: str, worlds: WorldRepository) -> dict:
    _stage(0, "正在读取企业已经公开的主张，不向 Agent 暴露事后答案。")
    world = create_negotiation_world(
        config.get("seed", 42), f"job-{CURRENT_JOB_ID}", "free", "plain", "llm",
    )
    world.model_name = model_name
    program = config.get("program", "adaptive_staged")
    _stage(1, "招商项目组正在决定先查资金、技术、客户还是信用。")
    case = DueDiligenceEngine(world).assess("firm_risky", program)
    _checkpoint(worlds, world, "重点项目尽调完成")
    _stage(2, "核验材料已经返回，系统正在比较企业主张与外部观察。")
    for turn in case.agent_turns:
        actor = world.agents.get(turn.get("actor_id"))
        _event(
            _action_label(turn.get("action_id", "项目核验")),
            turn.get("rationale", "基于当前证据选择下一项核验。"),
            actor=actor.name if actor else "项目尽调组",
        )
    for evidence in case.evidence:
        _event(
            "获得一项可核验证据",
            _evidence_narrative(evidence),
            actor=world.agents[evidence.requested_by].name,
            tone="warning" if evidence.conflict > 0.2 else "success",
        )
    _stage(3, "市级项目决策组正在基于证据决定推进、试点、补证还是否决。")
    metrics = due_diligence_metrics([case])
    report = {
        "schema_version": "1.0",
        "research_question": "面对没有答案标签的新企业，什么程序更有助于识别风险？",
        "configuration": {
            "seeds": [world.seed], "programs": [program], "thresholds": [world.due_diligence_threshold],
            "mode": "llm", "model_name": model_name, "hidden_label_visible_to_agents": False,
        },
        "agent_runtime": _runtime(world, model_name),
        "program_summary": [{
            "id": program, "name": _program_label(program), "description": "本次公众单项目实时尽调",
            "runs": 1, "metrics": {key: {"mean": float(metrics.get(key, 0)), "variance": 0.0}
                                      for key in ("precision", "recall", "specificity", "brier_score")},
            "action_counts": {},
        }],
        "program_runs": [{"program": program, "seed": world.seed, **metrics,
                          "cases": [case_payload(world, case)]}],
        "threshold_curve": [],
        "interpretation_boundary": "这是程序压力测试，不是对现实企业的信用评级。",
    }
    _stage(4, "正在生成一份不使用技术黑话的项目判断说明。")
    return report


def _conversation(config: dict[str, Any], model_name: str, worlds: WorldRepository) -> dict:
    _stage(0, "正在把你输入的新情况转换成谁先知道、谁还不知道的局势。")
    _event("信息边界已建立", "新情况只会先被能够观察到它的主体知道，不会自动全员共享。")
    _stage(1, "项目组正在选择最值得先核验的证据。")
    world, report = run_conversation_experience(
        worlds, config.get("mechanism_id", "M8"), config.get("event_text", "企业融资计划发生变化。"),
        config.get("seed", 42), "llm", model_name,
    )
    _checkpoint(worlds, world, "协商与证据链完成")
    _stage(2, "企业与政府正在依据各自掌握的信息作出回应。")
    for item in report["timeline"]:
        actor = world.agents.get(item.get("actor_id"))
        _event(
            _action_label(item.get("action", "协商行动")), item.get("detail", "形成新的协商状态。"),
            actor=actor.name if actor else "协商参与方",
        )
    _stage(3, "规则引擎正在检查承诺、证据和财政边界。")
    _event("形成当前程序决定", f"本轮结果是“{_decision_label(report['result']['decision'])}”。这不是永久标签，而是对当前证据的回应。", actor="InsideGov规则引擎")
    _stage(4, "正在整理本轮证据链和可以复核的行动依据。")
    return report


def _dynamic(config: dict[str, Any], model_name: str, worlds: WorldRepository) -> dict:
    policy = config.get("policy", "conditional")
    _stage(0, "正在建立产业扩张、企业经营和地方财政相互影响的世界。")
    checkpoint = JOB_REPOSITORY.get(CURRENT_JOB_ID).get("checkpoint") if JOB_REPOSITORY else None
    resumed_world = worlds.load(checkpoint["world_id"]) if checkpoint and checkpoint.get("world_id") else None
    if resumed_world is not None:
        parent_id = resumed_world.id
        resumed_world.id = f"job-{CURRENT_JOB_ID}"
        resumed_world.parent_id = parent_id
        resumed_world.name = "动态竞争实验（续跑）"

    def progress(info: dict[str, Any], world) -> None:
        quarter = info["quarter"]
        if quarter < 9:
            index, message = 1, f"产业正在扩张，当前推进到第 {quarter} 季度。"
        elif quarter == 10:
            index, message = 2, "市场需求冲击已经发生，企业经营压力开始显现。"
        elif quarter < info["quarters"]:
            index, message = 3, f"政府与企业正在处理救助、重组和退出，当前为第 {quarter} 季度。"
        else:
            index, message = 4, "正在结算就业、产能利用率和财政支出。"
        job = JOB_REPOSITORY.get(CURRENT_JOB_ID)
        if job["stage_index"] != index:
            _stage(index, message)
        else:
            JOB_REPOSITORY.update(CURRENT_JOB_ID, message=message, heartbeat_at=time.time())
        _checkpoint(worlds, world, f"Q{quarter} 跨期结算完成")
        for item in info["new_events"][-3:]:
            _event(item.get("title", "世界发生变化"), item.get("detail", "状态已经更新。"),
                   actor="产业世界", tone=item.get("severity", "neutral"))

    return run_dynamic_competition_experiment(
        seed=config.get("seed", 42), quarters=config.get("quarters", 16), demand_shock=-0.42,
        policy_ids=[policy], mode="llm", model_name=model_name,
        progress_callback=progress, cancel_check=_cancel_requested,
        initial_world=resumed_world,
    )


def _story_turn(config: dict[str, Any], _model_name: str, worlds: WorldRepository) -> dict:
    _stage(0, "系统正在读取你的角色、权限和公开表态。")
    sessions = StorySessionRepository()
    session = sessions.load(config["session_id"])
    if session is None:
        raise ValueError("故事会话已经失效，请重新选择角色。")
    world = worlds.load(session.world_id)
    if world is None:
        raise ValueError("故事世界不存在，请重新开始。")
    engine = SimulationEngine(world)
    _stage(1, "其他组织正在根据各自掌握的信息自主回应你的行动。")
    result = take_story_turn(
        engine, session, sessions, worlds, config["action_id"], config.get("statement", ""),
    )
    _checkpoint(worlds, engine.world, f"第 {session.turn_count} 回合完成")
    _stage(2, "权限和程序检查已经完成，正在确认你的行动是否可以执行。")
    receipt = result.get("receipt") or {}
    _event(
        "你的行动已被执行" if receipt.get("status") == "executed" else "你的行动被规则拦下",
        (receipt.get("executed_action") or {}).get("selection_rationale") or receipt.get("rule_statement", "本回合已经结算。"),
        actor=result["player"]["name"], tone="success" if receipt.get("status") == "executed" else "warning",
    )
    _stage(4, "正在把本回合改写成容易理解的组织故事。")
    return result


def _runtime(world, model_name: str) -> dict[str, Any]:
    return {
        "mode": "llm", "model_name": model_name,
        "providers": sorted({item.provider for item in world.action_audits if item.provider}),
        "audited_agent_decisions": len(world.action_audits),
        "fallback_count": sum(bool(item.fallback) for item in world.action_audits),
        "fixed_for_public_experience": True,
    }


def _action_label(action: str) -> str:
    return {
        "verify_funding_sources": "核验资金来源", "technical_expert_review": "技术专家评审",
        "customer_contract_check": "核验客户合同", "credit_and_litigation_check": "信用与诉讼核查",
        "team_delivery_reference": "核查团队交付记录", "red_team_challenge": "进行反方质询",
        "approve": "正式推进", "conditional_pilot": "先做可逆试点", "defer": "补证后再议",
        "reject": "本轮不进入签约", "accept": "接受方案", "counter": "提出还价",
        "terminate": "退出谈判",
    }.get(action, action)


def _decision_label(decision: str) -> str:
    return {"approve": "正式推进", "conditional_pilot": "先做可逆试点", "defer": "补证后再议", "reject": "本轮不进入签约"}.get(decision, decision)


def _program_label(program: str) -> str:
    return {"light_screen": "轻量筛查", "clarification_only": "澄清优先", "independent_verification": "独立核验", "red_team": "反方质询", "adaptive_staged": "自适应核验与试点"}.get(program, program)


def _evidence_narrative(evidence) -> str:
    dimension = {
        "financing": "资金能否真正闭合", "technology": "技术成熟度",
        "market": "市场是否已经验证", "governance": "治理与信用",
        "execution": "团队交付能力",
    }.get(evidence.dimension, evidence.dimension)
    quality = "偏弱" if evidence.observed_quality < 0.4 else "仍需观察" if evidence.observed_quality < 0.65 else "较有支撑"
    reliability = "来源较可靠" if evidence.reliability >= 0.75 else "主要来自企业材料"
    conflict = "与企业说法存在明显差异" if evidence.conflict >= 0.3 else "与企业说法有一定出入" if evidence.conflict >= 0.15 else "与企业说法基本一致"
    return f"对“{dimension}”的核验显示：当前证据{quality}；{reliability}，但{conflict}。"


def run_job(database: str, job_id: str) -> None:
    global JOB_REPOSITORY, CURRENT_JOB_ID
    JOB_REPOSITORY = PublicJobRepository(database)
    CURRENT_JOB_ID = job_id
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    job = JOB_REPOSITORY.get(job_id)
    JOB_REPOSITORY.update(
        job_id, status="running", pid=os.getpid(), started_at=time.time(), heartbeat_at=time.time(),
        message="独立推演进程已经启动。",
    )
    JOB_REPOSITORY.event(job_id, "job.started", 0, "推演已经开始", "任务不依赖当前网页连接，可以安全离开。")
    heartbeat = threading.Thread(target=_heartbeat, name=f"heartbeat-{job_id}", daemon=True)
    heartbeat.start()
    worlds = WorldRepository()
    runners = {
        "coordination": _coordination, "diligence": _diligence,
        "dynamic_competition": _dynamic, "conversation": _conversation,
        "story_turn": _story_turn,
    }
    try:
        result = runners[job["scene"]](job["config"], job["model_name"], worlds)
        JOB_REPOSITORY.update(
            job_id, status="completed", result=result, finished_at=time.time(), pid=None,
            stage_index=4, stage_label=job["stages"][-1], message="推演完成，结果和过程记录已经保存。",
        )
        JOB_REPOSITORY.event(job_id, "job.completed", 4, "推演完成", "你可以查看结果，也可以复制条件再跑一次。", tone="success")
    except InterruptedError:
        _handle_stop(signal.SIGTERM, None)
    except Exception as exc:  # noqa: BLE001 - failures must become durable user-facing state
        current = JOB_REPOSITORY.get(job_id)
        JOB_REPOSITORY.update(
            job_id, status="failed", error=f"{type(exc).__name__}: {str(exc)[:500]}",
            finished_at=time.time(), pid=None,
            message="这一阶段没有完成，但此前已经保存的内容仍然可用。",
        )
        JOB_REPOSITORY.event(
            job_id, "job.failed", current["stage_index"], "这一阶段没有完成",
            "系统保留了之前的行动和检查点。你可以从最近节点重试，不必重新填写条件。",
            tone="danger",
        )
    finally:
        STOP_HEARTBEAT.set()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--database", required=True)
    args = parser.parse_args()
    run_job(args.database, args.job_id)


if __name__ == "__main__":
    main()
