"use client";

import { useEffect, useState } from "react";
import { API_BASE, api, type ExperimentReport, type ExperimentReportSummary, type ExperimentRun, type World } from "../lib/api";

export function ReportCenter({ remember }: { remember: (world: World) => void }) {
  const [reports, setReports] = useState<ExperimentReportSummary[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [report, setReport] = useState<ExperimentReport | null>(null);
  const [group, setGroup] = useState<"strategy" | "ablation">("strategy");
  const [run, setRun] = useState<ExperimentRun | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let alive = true;
    void api.listExperimentReports().then((items) => {
      if (!alive) return;
      setReports(items);
      const preferred = items.find((item) => item.kind === "p1_matrix") ?? items[0];
      if (preferred) setSelectedId(preferred.id);
    }).catch((caught) => setError(String(caught)));
    return () => { alive = false; };
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    let alive = true;
    void api.getExperimentReport(selectedId).then((result) => {
      if (alive) setReport(result);
    }).catch((caught) => setError(String(caught)));
    return () => { alive = false; };
  }, [selectedId]);

  const summaries = group === "strategy" ? report?.strategy_summary ?? [] : report?.ablation_summary ?? [];
  const runs = group === "strategy" ? report?.strategy_runs ?? [] : report?.ablation_runs ?? [];
  const maxEmployment = Math.max(1, ...summaries.map((item) => metric(item, "total_employment", "employment")));

  function selectReport(id: string) {
    setSelectedId(id);
    setReport(null);
    setRun(null);
  }

  async function openRunWorld(selected: ExperimentRun) {
    if (!report || !selected.world_available) return;
    remember(await api.getExperimentWorld(report.report_id, selected.world_id));
  }

  return <div className="report-center" data-testid="report-center">
    <small>EXPERIMENT EVIDENCE CENTER</small>
    <h2>可视化实验报告与 seed 下钻</h2>
    <div className="report-toolbar">
      <label>实验报告<select value={selectedId} onChange={(event) => selectReport(event.target.value)}>{reports.map((item) => <option key={item.id} value={item.id}>{item.title} · {item.strategy_runs + item.ablation_runs} runs</option>)}</select></label>
      <div><button className={group === "strategy" ? "active" : ""} onClick={() => { setGroup("strategy"); setRun(null); }}>策略比较</button><button className={group === "ablation" ? "active" : ""} onClick={() => { setGroup("ablation"); setRun(null); }}>机制消融</button></div>
      {report && <a href={`${API_BASE}/experiment-reports/${report.report_id}/download`}>导出 JSON</a>}
    </div>
    {error && <p className="error-text">{error}</p>}
    {!report && <p className="hint">正在读取实验报告…</p>}
    {report && <>
      <div className="report-meta"><span>{String(report.generated_at ?? "发布内置报告")}</span><span>{runs.length} 个可下钻运行</span><span>{report.failure_cases.length} 个失败案例</span></div>
      <div className="summary-chart">{summaries.map((item, index) => {
        const employment = metric(item, "total_employment", "employment");
        const cluster = metric(item, "cluster_size", "cluster");
        const label = item.name ?? item.strategy ?? item.mechanism ?? item.id ?? `实验 ${index + 1}`;
        return <button key={`${label}-${index}`} onClick={() => setRun(runs.find((candidate) => candidate.strategy === item.id) ?? null)}>
          <span>{label}</span><i><b style={{ width: `${employment / maxEmployment * 100}%` }} /></i><strong>{employment.toFixed(1)} 就业</strong><small>{cluster.toFixed(1)} 家集群 · n={sampleSize(item)}</small>
        </button>;
      })}</div>
      {runs.length > 0 ? <div className="seed-grid">{runs.map((item) => <button key={`${item.strategy}-${item.seed}`} className={run === item ? "active" : item.successful ? "" : "failed"} onClick={() => setRun(item)}>
        <strong>Seed {item.seed}</strong><span>{item.strategy}</span><small>{item.successful ? `${item.cluster_size} 家 · ${item.total_employment} 就业` : "失败/发生降级"}</small>
      </button>)}</div> : <p className="boundary">内置发布报告只包含聚合数据。运行 <code>uv run insidegov matrix</code> 后，这里会自动出现每个 seed 及其完整世界。</p>}
      {run && <article className="run-detail">
        <header><div><small>SINGLE RUN</small><h3>{run.strategy} · Seed {run.seed}</h3></div><span className={run.successful ? "success" : "danger"}>{run.successful ? "成功样本" : "失败样本"}</span></header>
        <div><p>选址<strong>{run.selected_city ?? "未落地"}</strong></p><p>就业<strong>{run.total_employment}</strong></p><p>集群<strong>{run.cluster_size}</strong></p><p>兑现<strong>{run.fulfilled_promises}</strong></p><p>信用<strong>{(run.average_credibility * 100).toFixed(1)}%</strong></p><p>方差来源<strong>Seed {run.seed}</strong></p></div>
        <button disabled={!run.world_available} onClick={() => void openRunWorld(run)}>{run.world_available ? "打开该 seed 完整博弈世界" : "该旧报告没有归档世界"}</button>
      </article>}
      <section className="failure-panel"><h3>失败与降级案例</h3>{report.failure_cases.length ? report.failure_cases.map((item, index) => <article key={`${item.strategy}-${item.seed}-${index}`}><b>{item.strategy} · Seed {item.seed}</b><span>{item.stage}</span><p>{item.reason}</p></article>) : <p>本报告没有失败记录。</p>}</section>
    </>}
  </div>;
}

function metric(item: ExperimentReport["strategy_summary"][number], key: string, fallback: "employment" | "cluster") {
  return item.metrics?.[key]?.mean ?? item[fallback] ?? 0;
}

function sampleSize(item: ExperimentReport["strategy_summary"][number]) {
  return item.metrics?.total_employment?.n ?? item.seeds ?? item.successful ?? 0;
}
