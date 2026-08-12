from __future__ import annotations

import html
import json
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import InterventionChange, InterventionPlan, WorldState

CITY_ALIASES = {
    "临江市": "city_lin", "临江": "city_lin",
    "海州市": "city_hai", "海州": "city_hai",
    "云麓市": "city_yun", "云麓": "city_yun",
}


def parse_intervention(text: str, current_quarter: int) -> InterventionPlan:
    """Parse a constrained intervention draft; execution happens only after confirmation."""
    target = next((city_id for name, city_id in CITY_ALIASES.items() if name in text), None)
    assumptions: list[str] = []
    if target is None:
        target = "city_lin"
        assumptions.append("未识别城市，暂按临江市处理")
    quarter_match = re.search(r"(?:第|Q)\s*(\d+)\s*(?:季度|季)?", text, re.IGNORECASE)
    effective_quarter = int(quarter_match.group(1)) if quarter_match else current_quarter + 1
    changes: list[InterventionChange] = []
    decline = re.search(
        r"(?:财政收入|可用财力|财政预算|预算)[^。；，,]{0,18}(?:下降|减少|降低)\s*(\d+(?:\.\d+)?)\s*%",
        text,
    )
    if decline:
        pct = float(decline.group(1)) / 100
        changes.append(InterventionChange(
            f"{target}.available_budget", "multiply", round(1 - pct, 4),
            f"可用财力下降 {pct:.0%}",
        ))
    increase = re.search(r"(?:增加|新增|提供|追加)[^\d]{0,8}(\d+(?:\.\d+)?)\s*亿", text)
    if increase:
        amount = float(increase.group(1))
        changes.append(InterventionChange(
            f"{target}.available_budget", "add", amount, f"新增专项资金 {amount:g} 亿元",
        ))
    credibility = re.search(r"(?:信用|信誉|履约)[^\d]{0,8}(?:提高|提升|增加)\s*(\d+(?:\.\d+)?)\s*%", text)
    if credibility:
        value = float(credibility.group(1)) / 100
        changes.append(InterventionChange(
            f"{target}.objective_credibility", "add", value, f"制度信誉提升 {value:.0%}",
        ))
    demand = re.search(r"需求[^\d]{0,8}(?:下降|减少|降低)\s*(\d+(?:\.\d+)?)\s*%", text)
    if demand:
        value = -float(demand.group(1)) / 100
        changes.append(InterventionChange(
            "market.demand_multiplier", "add", value, f"市场需求下降 {-value:.0%}",
        ))
    if not changes:
        assumptions.append("未识别可执行的白名单参数变化，需要人工补充")
    priority = "equipment_ordered" if "设备" in text and ("优先" in text or "保障" in text) else None
    return InterventionPlan(
        id=f"intervention-plan-{uuid.uuid4().hex[:8]}", source_text=text,
        effective_quarter=max(current_quarter + 1, effective_quarter), changes=changes,
        assumptions=assumptions, promise_priority=priority,
    )


def grounded_interview(world: WorldState, agent_id: str, question: str) -> dict[str, Any]:
    if agent_id not in world.agents:
        raise KeyError("agent not found in selected snapshot")
    agent = world.agents[agent_id]
    audits = [item for item in world.action_audits if item.agent_id == agent_id]
    memories = [item for item in agent.memories if item.quarter <= world.quarter]
    related = audits[-3:]
    known = [f"Q{item.quarter}观察：{json.dumps(item.observation, ensure_ascii=False)}" for item in related]
    known.extend(f"Q{item.quarter}记忆：{item.content}" for item in memories[-3:])
    unknown = ["其他主体未披露的私有底线", "所选季度之后发生的事件"]
    private_fields = sorted(agent.private_facts)
    if related:
        latest = related[-1]
        answer = (
            f"截至Q{world.quarter}，我基于当时可见信息作出“{latest.action_type}”。"
            f"理由是：{latest.rationale}。规则引擎随后执行为："
            f"{json.dumps(latest.executed_action, ensure_ascii=False)}。"
        )
        if latest.reflection:
            answer += f"我的当时复盘是：{latest.reflection}。"
    else:
        answer = f"截至Q{world.quarter}，没有找到我对该问题的已执行行动记录，不能补写原因。"
    if "如果" in question or "会" in question:
        answer += " 对问题中的反事实部分，我只能给出假设性判断；需要创建分支运行后才能确认结果。"
    return {
        "world_id": world.id, "quarter": world.quarter, "agent_id": agent_id,
        "question": question, "answer": answer,
        "knowledge_labels": {
            "known_at_the_time": known,
            "private_fields_used": private_fields,
            "unknown_at_the_time": unknown,
            "hindsight": [],
            "hypothetical": "如果" in question or "会" in question,
        },
        "evidence_audit_ids": [item.id for item in related],
    }


def compare_worlds(baseline: WorldState, branch: WorldState) -> dict[str, Any]:
    def final(world: WorldState) -> dict[str, float]:
        if not world.history:
            return {"employment": 0, "cluster": 0, "credibility": 0, "spending": 0}
        row = world.history[-1]
        return {
            "employment": row.total_employment, "cluster": row.cluster_size,
            "credibility": row.average_credibility,
            "spending": row.total_committed_expenditure,
        }
    base, changed = final(baseline), final(branch)
    return {
        "baseline": {"world_id": baseline.id, "quarter": baseline.quarter, "metrics": base},
        "branch": {"world_id": branch.id, "quarter": branch.quarter, "metrics": changed},
        "delta": {key: round(changed[key] - base[key], 6) for key in base},
        "event_difference": [asdict(item) for item in branch.events[len(baseline.events):]],
        "causal_chain": causal_chain(branch),
    }


def causal_chain(world: WorldState) -> list[dict[str, Any]]:
    chain: list[dict[str, Any]] = []
    for event in world.events:
        if event.kind in {"intervention", "external_shock", "negotiation", "promise", "location", "milestone"}:
            chain.append({
                "quarter": event.quarter, "cause": event.title, "effect": event.detail,
                "evidence": f"event:{event.quarter}:{event.kind}",
            })
    return chain[-12:]


def render_world_report(world: WorldState, comparison: dict[str, Any] | None = None) -> str:
    metrics = asdict(world.history[-1]) if world.history else {}
    failures = [item for item in world.events if item.kind == "model_fallback"]
    audits = world.action_audits
    repaired = sum(1 for item in audits for row in item.diagnostics if row.get("repaired"))
    retries = sum(1 for item in audits for row in item.diagnostics if row.get("outcome") == "retry")
    rows = "".join(
        f"<tr><td>Q{item.quarter}</td><td>{html.escape(item.agent_id)}</td>"
        f"<td>{html.escape(item.action_type)}</td><td>{html.escape(item.rationale)}</td>"
        f"<td>{'是' if item.fallback else '否'}</td></tr>" for item in audits[-30:]
    )
    chain = "".join(
        f"<li><b>Q{item['quarter']} {html.escape(item['cause'])}</b> → {html.escape(item['effect'])}</li>"
        for item in causal_chain(world)
    ) or "<li>暂无关键因果事件。</li>"
    comparison_html = ""
    if comparison:
        comparison_html = (
            "<h2>基线与分支差异</h2><pre>" +
            html.escape(json.dumps(comparison, ensure_ascii=False, indent=2)) + "</pre>"
        )
    return f"""<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>{html.escape(world.name)}实验报告</title>
<style>body{{font:15px/1.7 system-ui;max-width:1040px;margin:40px auto;padding:0 24px;color:#182124}}h1,h2{{line-height:1.25}}.cards{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.card{{padding:16px;background:#eef6f5;border-left:4px solid #138a86}}table{{width:100%;border-collapse:collapse}}td,th{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}pre{{white-space:pre-wrap;background:#f5f5f5;padding:16px}}.note{{background:#fff5db;padding:14px}}</style>
<body><h1>{html.escape(world.name)}：自动实验报告</h1><p>世界 {world.id} · seed {world.seed} · Q{world.quarter} · {html.escape(world.model_name or world.policy_mode)}</p>
<p class="note">本报告解释模拟内部因果链，不构成现实政策效果估计。</p>
<h2>世界卡</h2><div class="cards"><div class="card">就业<br><b>{metrics.get('total_employment', 0)}</b></div><div class="card">集群<br><b>{metrics.get('cluster_size', 0)}</b></div><div class="card">财政承诺<br><b>{metrics.get('total_committed_expenditure', 0)}</b></div><div class="card">信用<br><b>{metrics.get('average_credibility', 0):.3f}</b></div></div>
<h2>关键因果链</h2><ol>{chain}</ol>{comparison_html}
<h2>Agent行动审计</h2><table><thead><tr><th>季度</th><th>Agent</th><th>行动</th><th>理由</th><th>降级</th></tr></thead><tbody>{rows}</tbody></table>
<h2>LLM质量</h2><p>审计行动 {len(audits)} 条；结构修复 {repaired} 次；重试 {retries} 次；最终降级 {len(failures)} 次。</p>
<h2>假设与限制</h2><ul><li>数值来自合成世界与当前参数，不可直接外推现实政策效应。</li><li>因果链是规则与事件日志的可审计解释，不是统计因果识别。</li><li>私有信息在公开报告中不展示具体值。</li></ul></body></html>"""


@dataclass(slots=True)
class MaterialParameter:
    id: str
    target: str
    evidence: str
    suggested_value: float
    final_value: float | None
    confidence: float
    provenance: str
    status: str = "pending"


@dataclass(slots=True)
class CandidateWorld:
    id: str
    filename: str
    content_excerpt: str
    entities: list[str]
    relations: list[dict[str, str]]
    parameters: list[MaterialParameter]
    missing_fields: list[str]
    status: str = "draft"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


def extract_candidate_world(filename: str, content: str) -> CandidateWorld:
    sentences = [item.strip() for item in re.split(r"[。！？\n]+", content) if item.strip()]
    entities = sorted(set(re.findall(r"[\u4e00-\u9fff]{2,8}(?:市|区|县|公司|集团|大学|研究院)", content)))
    relations: list[dict[str, str]] = []
    for sentence in sentences:
        mentioned = [entity for entity in entities if entity in sentence]
        if len(mentioned) >= 2:
            relations.append({
                "source": mentioned[0], "target": mentioned[1],
                "relation": "材料中共同出现", "evidence": sentence[:500],
            })
    parameters: list[MaterialParameter] = []
    patterns = [
        (r"(?:财政|专项资金|可用财力)[^\d]{0,12}(\d+(?:\.\d+)?)\s*亿", "city_lin.available_budget", "public_source"),
        (r"(?:供应链|产业基础)[^\d]{0,12}(\d+(?:\.\d+)?)", "city_lin.supply_chain", "public_source"),
        (r"(?:人才|人才池)[^\d]{0,12}(\d+(?:\.\d+)?)", "city_lin.talent_pool", "public_source"),
        (r"(?:信誉|信用|履约率)[^\d]{0,12}(\d+(?:\.\d+)?)\s*%", "city_lin.objective_credibility", "public_source"),
    ]
    for pattern, target, provenance in patterns:
        match = re.search(pattern, content)
        if not match:
            continue
        raw = float(match.group(1))
        value = raw / 100 if target.endswith("credibility") else raw
        evidence = next((sentence for sentence in sentences if match.group(0) in sentence), match.group(0))
        parameters.append(MaterialParameter(
            id=f"parameter-{len(parameters)+1:03d}", target=target,
            evidence=evidence[:500], suggested_value=value, final_value=None,
            confidence=0.82, provenance=provenance,
        ))
    found = {item.target for item in parameters}
    required = {
        "city_lin.available_budget", "city_lin.supply_chain",
        "city_lin.talent_pool", "city_lin.objective_credibility",
    }
    for target, default in {
        "city_lin.available_budget": 120.0, "city_lin.supply_chain": 55.0,
        "city_lin.talent_pool": 58.0, "city_lin.objective_credibility": 0.72,
    }.items():
        if target not in found:
            parameters.append(MaterialParameter(
                id=f"parameter-{len(parameters)+1:03d}", target=target,
                evidence="材料未提供直接证据", suggested_value=default, final_value=None,
                confidence=0.25, provenance="demo_assumption",
            ))
    return CandidateWorld(
        id=f"candidate-{uuid.uuid4().hex[:8]}", filename=filename,
        content_excerpt=content[:1200], entities=entities, relations=relations,
        parameters=parameters, missing_fields=sorted(required - found),
    )


class CandidateRepository:
    def __init__(self, root: str | Path = ".insidegov/candidates"):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, candidate: CandidateWorld) -> None:
        (self.root / f"{candidate.id}.json").write_text(
            json.dumps(asdict(candidate), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def load(self, candidate_id: str) -> CandidateWorld | None:
        path = self.root / f"{candidate_id}.json"
        if not path.exists():
            return None
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["parameters"] = [MaterialParameter(**item) for item in raw["parameters"]]
        return CandidateWorld(**raw)
