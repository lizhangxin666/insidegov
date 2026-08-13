"use client";

import { useEffect, useMemo, useState } from "react";
import {
  api,
  type DynamicCompetitionReport,
  type DynamicRescueDecision,
} from "../lib/api";

const decisionNames: Record<string, string> = {
  market_exit: "市场退出",
  unconditional_rescue: "无条件救助",
  conditional_rescue: "附条件救助",
  unconditional: "无条件救助",
  conditional: "附条件救助",
  reject_rescue: "拒绝救助",
  aggressive_imitation: "激进模仿",
  targeted_imitation: "定向模仿",
  blocked: "被硬约束拦截",
};

export function DynamicCompetitionLab() {
  const [report, setReport] = useState<DynamicCompetitionReport | null>(null);
  const [selected, setSelected] = useState("conditional");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  async function run() {
    setBusy(true);
    setError("");
    try {
      setReport(await api.dynamicCompetition());
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    let alive = true;
    void api
      .dynamicCompetition()
      .then((result) => {
        if (alive) setReport(result);
      })
      .catch((caught) => {
        if (alive) setError(String(caught));
      })
      .finally(() => {
        if (alive) setBusy(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const current = useMemo(
    () => report?.variants.find((item) => item.id === selected),
    [report, selected],
  );
  const sampleRescue = current?.rescue_decisions.find(
    (item) => item.decision !== "reject_rescue",
  ) ?? current?.rescue_decisions[0];

  if (busy)
    return (
      <section className="dynamic-lab loading">
        <small>DYNAMIC COMPETITION · SAME SEED</small>
        <h2>正在运行三种退出与救助制度…</h2>
        <p>共同随机种子、共同城市模仿、共同 Q10 需求冲击，仅改变救助制度。</p>
      </section>
    );
  if (error || !report)
    return (
      <section className="dynamic-lab">
        <small>DYNAMIC COMPETITION</small>
        <h2>实验未完成</h2>
        <p className="error-text">{error}</p>
        <button onClick={() => void run()}>重新运行</button>
      </section>
    );

  return (
    <section className="dynamic-lab">
      <header>
        <div>
          <small>DYNAMIC COMPETITION · SEED {report.seed}</small>
          <h2>城市模仿 → 产能过剩 → 企业退出与政府救助</h2>
          <p>
            Q10 需求下降 {Math.abs(report.common_conditions.demand_shock * 100).toFixed(0)}%，
            三个世界只改变救助制度。
          </p>
        </div>
        <span>24 季度真实规则推演</span>
      </header>

      <ol className="causal-ribbon">
        {report.causal_chain.map((item, index) => (
          <li key={item}>
            <i>{index + 1}</i>
            <span>{item}</span>
          </li>
        ))}
      </ol>

      <div className="policy-cards">
        {report.variants.map((variant) => (
          <button
            key={variant.id}
            className={variant.id === selected ? "active" : ""}
            onClick={() => setSelected(variant.id)}
          >
            <small>制度 {variant.id === "market_exit" ? "A" : variant.id === "unconditional" ? "B" : "C"}</small>
            <h3>{variant.name}</h3>
            <p>{variant.description}</p>
            <div>
              <span>
                就业 <b>{variant.final.total_employment.toLocaleString()}</b>
              </span>
              <span>
                退出 <b>{variant.final.exited_firms}</b>
              </span>
              <span>
                僵尸 <b>{variant.final.zombie_firms}</b>
              </span>
              <span>
                救助 <b>{variant.final.rescue_spending.toFixed(1)}亿</b>
              </span>
            </div>
          </button>
        ))}
      </div>

      {current && (
        <div className="dynamic-evidence">
          <section>
            <h3>{current.name}：季度演化</h3>
            <div className="trajectory-chart">
              {current.trajectory.map((item) => (
                <div key={item.quarter} title={`Q${item.quarter} 利用率 ${(item.utilization * 100).toFixed(0)}%`}>
                  <i style={{ height: `${Math.max(3, item.utilization * 100)}%` }} />
                  <span>Q{item.quarter}</span>
                </div>
              ))}
            </div>
            <div className="evolution-stats">
              <span>模仿项目 <b>{current.final.imitation_projects}</b></span>
              <span>模仿产能 <b>{current.final.imitation_capacity.toFixed(1)}</b></span>
              <span>期末总产能 <b>{current.final.capacity.toFixed(1)}</b></span>
              <span>期末利用率 <b>{(current.final.utilization * 100).toFixed(1)}%</b></span>
            </div>
          </section>
          <section>
            <h3>一次真实救助会商</h3>
            {sampleRescue ? <RescueMeeting decision={sampleRescue} /> : <p>该制度下没有发生救助会商。</p>}
          </section>
        </div>
      )}

      <div className="dynamic-conclusion">
        {Object.entries(report.headline_comparison).map(([key, value]) => (
          <p key={key}><b>{decisionNames[key] ?? key}</b>{value}</p>
        ))}
      </div>
      <p className="boundary">{report.interpretation_boundary}</p>
    </section>
  );
}

function RescueMeeting({ decision }: { decision: DynamicRescueDecision }) {
  return (
    <div className="rescue-meeting">
      <div className="meeting-limit">
        <span>企业申请 <b>{decision.requested_amount.toFixed(1)} 亿</b></span>
        <span>财政硬上限 <b>{decision.finance_limit.toFixed(1)} 亿</b></span>
        <span>最终执行 <b>{decision.approved_amount.toFixed(1)} 亿</b></span>
      </div>
      {decision.turns.map((turn, index) => (
        <article key={`${turn.actor_id}-${index}`}>
          <small>{turn.actor_id}</small>
          <strong>{decisionNames[turn.act ?? ""] ?? turn.act}</strong>
          <p>{turn.summary}</p>
        </article>
      ))}
      <div className="rule-settlement">
        <small>RULE ENGINE SETTLEMENT</small>
        <p>
          产能 {decision.capacity_before.toFixed(1)} → {decision.capacity_after.toFixed(1)}；
          岗位 {decision.jobs_before} → {decision.jobs_after}。
        </p>
      </div>
    </div>
  );
}
