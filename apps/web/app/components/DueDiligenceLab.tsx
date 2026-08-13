"use client";

import { useEffect, useMemo, useState } from "react";
import {
  api,
  type DueDiligenceCase,
  type DueDiligenceReport,
} from "../lib/api";

const decisions: Record<string, string> = {
  approve: "正式推进",
  conditional_pilot: "可逆试点",
  defer: "补证后再议",
  reject: "签约前否决",
};
const dimensionNames: Record<string, string> = {
  financing: "资金闭合",
  technology: "技术成熟",
  market: "市场验证",
  governance: "治理信用",
  execution: "交付能力",
};

export function DueDiligenceLab() {
  const [report, setReport] = useState<DueDiligenceReport | null>(null);
  const [program, setProgram] = useState("adaptive_staged");
  const [seed, setSeed] = useState(3);
  const [firmId, setFirmId] = useState("firm_risky");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    void api.dueDiligence()
      .then((value) => {
        if (!alive) return;
        setReport(value);
        setSeed(value.configuration.seeds[0]);
      })
      .catch((caught) => alive && setError(String(caught)))
      .finally(() => alive && setBusy(false));
    return () => { alive = false; };
  }, []);

  const run = useMemo(
    () => report?.program_runs.find((item) => item.program === program && item.seed === seed),
    [program, report, seed],
  );
  const current = useMemo(
    () => run?.cases.find((item) => item.firm_id === firmId) ?? run?.cases[0],
    [firmId, run],
  );
  const contrast = useMemo(() => {
    if (!report) return [];
    return ["light_screen", "independent_verification", "adaptive_staged"].map((id) => {
      const row = report.program_runs.find((item) => item.program === id && item.seed === seed);
      return row?.cases.find((item) => item.firm_id === "firm_risky");
    }).filter((item): item is DueDiligenceCase => Boolean(item));
  }, [report, seed]);

  if (busy) return <section className="diligence-lab loading"><small>EVIDENCE-GATED DUE DILIGENCE</small><h2>正在运行 5 种程序 × 8 个随机种子…</h2></section>;
  if (error || !report) return <section className="diligence-lab"><h2>研究矩阵未完成</h2><p className="error-text">{error}</p></section>;

  return (
    <section className="diligence-lab">
      <header>
        <div><small>UNKNOWN FIRM · NO ORACLE LABEL</small><h2>面对没有答案标签的新企业，什么程序更有识别力？</h2><p>{report.research_question}</p></div>
        <span>Agent 看不到真实质量 ✓</span>
      </header>

      <div className="diligence-programs">
        {report.program_summary.map((item) => (
          <button key={item.id} className={program === item.id ? "active" : ""} onClick={() => setProgram(item.id)}>
            <small>{item.runs} SEEDS</small><strong>{item.name}</strong><p>{item.description}</p>
            <div><span>识别失败项目 <b>{pct(item.metrics.recall.mean)}</b></span><span>不误伤好项目 <b>{pct(item.metrics.specificity.mean)}</b></span><span>尽调成本 <b>{item.metrics.diligence_cost.mean.toFixed(1)}</b></span></div>
          </button>
        ))}
      </div>

      <section className="diligence-contrast">
        <header><h3>同一企业、同一 Seed，只改变证据程序</h3><select value={seed} onChange={(event) => setSeed(Number(event.target.value))}>{report.configuration.seeds.map((value) => <option key={value}>{value}</option>)}</select></header>
        <div>
          {contrast.map((item) => <article key={item.program}><small>{report.program_summary.find((row) => row.id === item.program)?.name}</small><strong className={item.decision}>{decisions[item.decision]}</strong><p>事前风险 {pct(item.estimated_failure_probability)} · 不确定性 {pct(item.uncertainty)}</p><span>{item.evidence.length} 项证据 / {item.elapsed_days} 天 / 成本 {item.diligence_cost.toFixed(2)}</span></article>)}
        </div>
      </section>

      <div className="diligence-detail">
        <section>
          <header><h3>证据链</h3><select value={current?.firm_id ?? ""} onChange={(event) => setFirmId(event.target.value)}>{run?.cases.map((item) => <option value={item.firm_id} key={item.firm_id}>{item.firm_name}</option>)}</select></header>
          {current?.evidence.map((item) => (
            <article key={item.id}>
              <i>R{item.round}</i><div><small>{item.requested_by} · {dimensionNames[item.dimension]}</small><strong>{item.source_type}</strong><p>{item.summary}</p></div><span>可靠度<b>{pct(item.reliability)}</b></span><span>材料主张<b>{pct(item.claim_value)}</b></span><span>核验观察<b>{pct(item.observed_quality)}</b></span>
            </article>
          ))}
        </section>
        <section>
          <h3>Agent 自主性与规则边界</h3>
          <ol>{current?.agent_turns.map((turn, index) => <li key={index}><i>{index + 1}</i><span><b>{String(turn.actor_id)}</b>{String(turn.action_id)}<small>{String(turn.rationale ?? "基于风险与信息价值选择下一步")}</small></span></li>)}</ol>
          {current && <div className="diligence-verdict"><small>FINAL DECISION</small><strong>{decisions[current.decision]}</strong><p>规则引擎没有替 Agent 判断项目好坏；只负责证据可见性、权限、硬红线和事后结算。</p><code>decision_used_hidden_label = {String(current.decision_used_hidden_label)}</code></div>}
        </section>
      </div>

      <section className="threshold-panel"><h3>阈值不是答案：它改变误放与误伤的取舍</h3><div>{report.threshold_curve.map((item) => <article key={item.threshold}><b>{item.threshold.toFixed(2)}</b><span className="catch" style={{height: `${item.true_positive_rate * 100}%`}} /><span className="hurt" style={{height: `${item.false_positive_rate * 100}%`}} /><small>抓到 {pct(item.true_positive_rate)}<br/>误伤 {pct(item.false_positive_rate)}</small></article>)}</div></section>
      <p className="boundary">{report.interpretation_boundary}</p>
    </section>
  );
}

function pct(value: number) { return `${(value * 100).toFixed(0)}%`; }
