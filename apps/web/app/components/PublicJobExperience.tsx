"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, api, type PublicJob, type PublicJobEvent } from "../lib/api";

const terminal = new Set(["completed", "failed", "canceled", "partial"]);

export function PublicJobRoom({
  jobId,
  onLeave,
  onResult,
  onJobChanged,
}: {
  jobId: string;
  onLeave: () => void;
  onResult: (job: PublicJob) => void | Promise<void>;
  onJobChanged?: (jobId: string) => void;
}) {
  const [job, setJob] = useState<PublicJob | null>(null);
  const [events, setEvents] = useState<PublicJobEvent[]>([]);
  const [error, setError] = useState("");
  const [actionBusy, setActionBusy] = useState(false);
  const cursor = useRef(0);

  const refresh = useCallback(async () => {
    const next = await api.getPublicJob(jobId);
    setJob(next);
    const additions = await api.getPublicJobEvents(jobId, cursor.current);
    if (additions.length) {
      cursor.current = additions.at(-1)?.sequence ?? cursor.current;
      setEvents((current) => mergeEvents(current, additions));
    }
  }, [jobId]);

  useEffect(() => {
    cursor.current = 0;
    setEvents([]);
    setJob(null);
    setError("");
    void refresh().catch((caught) => setError(readableError(caught)));
    const poll = window.setInterval(() => {
      void refresh().catch((caught) => setError(readableError(caught)));
    }, 2500);
    const source = new EventSource(`${API_BASE}/experience/jobs/${jobId}/stream?after=0`);
    const receive = (message: MessageEvent) => {
      if (!message.data) return;
      try {
        const item = JSON.parse(message.data) as PublicJobEvent;
        if (!item.sequence) return;
        cursor.current = Math.max(cursor.current, item.sequence);
        setEvents((current) => mergeEvents(current, [item]));
      } catch {
        // Terminal events only carry status; polling retrieves final state.
      }
    };
    for (const name of ["job.queued", "job.started", "job.resuming", "job.retry", "stage.started", "progress", "job.completed", "job.failed", "job.canceling", "job.canceled"]) {
      source.addEventListener(name, receive as EventListener);
    }
    source.addEventListener("terminal", () => void refresh());
    source.onerror = () => {
      source.close();
      // The polling path keeps the room recoverable when a stream is interrupted.
    };
    return () => {
      window.clearInterval(poll);
      source.close();
    };
  }, [jobId, refresh]);

  async function cancel() {
    if (!job) return;
    setActionBusy(true);
    try { setJob(await api.cancelPublicJob(job.id)); }
    catch (caught) { setError(readableError(caught)); }
    finally { setActionBusy(false); }
  }

  async function retry() {
    if (!job) return;
    setActionBusy(true);
    try {
      const next = await api.retryPublicJob(job.id);
      onJobChanged?.(next.id);
    } catch (caught) { setError(readableError(caught)); }
    finally { setActionBusy(false); }
  }

  if (!job) return <section className="public-run-loading"><div className="running-orbit"><i /><i /><b>内</b></div><h2>正在找到这次推演…</h2><p>{error || "任务记录保存在本地，即使页面刚刚刷新也不会丢失。"}</p></section>;

  const status = statusCopy(job.status);
  const latest = terminal.has(job.status)
    ? events.at(-1)
    : [...events].reverse().find((item) => item.event_type === "progress") ?? events.at(-1);
  const canStop = ["queued", "running", "waiting_user", "canceling"].includes(job.status);
  const canRetry = ["failed", "canceled", "partial"].includes(job.status);
  return <main className="public-run-room">
    <header className="run-room-header">
      <button onClick={onLeave}>← 暂时离开</button>
      <div><small>这次推演会在后台继续</small><h1>{job.title}</h1><p>{status.description}</p></div>
      <span className={`run-status-pill ${job.status}`}><i />{status.label}</span>
    </header>

    <section className="run-stage-layout">
      <aside className="run-stage-rail">
        <small>事情进展到哪里</small>
        <ol>{job.stages.map((stage, index) => {
          const state = job.status === "completed" || index < job.stage_index ? "done" : index === job.stage_index ? "current" : "future";
          return <li key={stage} className={state}><i>{state === "done" ? "✓" : index + 1}</i><span><b>{stage}</b><small>{state === "done" ? "已经完成" : state === "current" ? "正在进行" : "尚未开始"}</small></span></li>;
        })}</ol>
        <div className="run-leave-note"><b>你不必留在这里</b><p>关闭网页或去看其他场景都不会中断推演。回来后会从最后一条记录继续显示。</p></div>
      </aside>

      <section className="run-live-stage">
        <header><small>此刻正在发生</small><h2>{latest?.title || job.stage_label}</h2><p>{latest?.detail || job.message}</p>{latest?.actor ? <span>{latest.actor}</span> : null}</header>
        <div className="run-event-feed">{events.length ? events.slice(-14).map((item) => <article key={item.sequence} className={item.tone}><i>{eventIcon(item)}</i><div><small>{item.actor || stageActor(item.event_type)}</small><b>{item.title}</b><p>{item.detail}</p></div><time>{timeOnly(item.created_at)}</time></article>) : <article className="thinking"><i>…</i><div><small>InsideGov</small><b>正在准备第一项行动</b><p>各主体只会看到自己有权知道的信息。</p></div></article>}</div>
      </section>

      <aside className="run-facts-panel">
        <small>这次运行</small>
        <div><span>已经用时<b>{duration(job.elapsed_seconds)}</b></span><span>过程记录<b>{job.event_count} 条</b></span><span>当前模型<b>{job.model_name}</b></span><span>恢复次数<b>{Math.max(0, job.attempt - 1)} 次</b></span></div>
        {job.checkpoint ? <section className="checkpoint-card"><i>✓</i><div><b>最近节点已保存</b><p>{job.checkpoint.note || `世界推进到第 ${job.checkpoint.quarter ?? "—"} 季度`}</p></div></section> : <section className="checkpoint-card pending"><i>○</i><div><b>等待首个安全节点</b><p>完成一个行动或季度后，系统会自动保存。</p></div></section>}
        {job.status === "completed" ? <button className="view-run-result" onClick={() => void onResult(job)}>查看这次推演的结论 →</button> : null}
        {canStop ? <button className="stop-run" disabled={actionBusy || job.status === "canceling"} onClick={() => void cancel()}>{job.status === "canceling" ? "正在安全停止…" : "安全停止并保留已有内容"}</button> : null}
        {canRetry ? <button className="view-run-result" disabled={actionBusy} onClick={() => void retry()}>从最近保存节点重新开始 →</button> : null}
        {job.status === "failed" ? <section className="plain-failure"><b>这一阶段没有完成</b><p>此前已经形成的行动和世界状态仍然保留。重新开始时只重做未完成部分。</p></section> : null}
        {error ? <p className="scenario-error">{error}</p> : null}
        <details><summary>查看运行依据</summary><p>任务编号：{job.id}</p><p>事件序号：{cursor.current}</p><p>尝试次数：{job.attempt}</p><p>最近心跳：{job.heartbeat_at ? timeOnly(job.heartbeat_at) : "尚未开始"}</p>{job.error ? <p>诊断：{job.error}</p> : null}</details>
      </aside>
    </section>
  </main>;
}

export function PublicTaskDock({ onOpen }: { onOpen: (jobId: string) => void }) {
  const [jobs, setJobs] = useState<PublicJob[]>([]);
  const [open, setOpen] = useState(false);
  const [notice, setNotice] = useState("");
  const previous = useRef<Map<string, PublicJob["status"]>>(new Map());
  useEffect(() => {
    const originalTitle = document.title;
    const load = () => void api.listPublicJobs(12).then((next) => {
      const completed = next.find((job) => {
        const before = previous.current.get(job.id);
        return before && !terminal.has(before) && job.status === "completed";
      });
      previous.current = new Map(next.map((job) => [job.id, job.status]));
      if (completed) {
        setNotice(`“${completed.title}”已经完成，可以查看结论了。`);
        setOpen(true);
        document.title = "推演完成 · InsideGov";
      }
      setJobs(next);
    }).catch(() => undefined);
    load();
    const timer = window.setInterval(load, 5000);
    return () => {
      window.clearInterval(timer);
      document.title = originalTitle;
    };
  }, []);
  if (!jobs.length) return null;
  const active = jobs.filter((job) => !terminal.has(job.status));
  return <aside className={`public-task-dock ${open ? "open" : ""}`}>
    {notice ? <button className="task-complete-notice" onClick={() => setNotice("")}><b>推演完成</b><span>{notice}</span><em>知道了</em></button> : null}
    <button className="task-dock-toggle" onClick={() => setOpen((value) => !value)}><i>{active.length || "✓"}</i><span><b>{active.length ? `${active.length} 个推演正在进行` : "最近的推演"}</b><small>{active.length ? "可以离开页面，完成后回来查看" : "运行记录已经保存"}</small></span><em>{open ? "收起" : "查看"}</em></button>
    {open ? <div>{jobs.map((job) => <button key={job.id} onClick={() => onOpen(job.id)}><i className={job.status} /><span><b>{job.title}</b><small>{statusCopy(job.status).label} · {job.stage_label}</small></span><time>{duration(job.elapsed_seconds)}</time></button>)}</div> : null}
  </aside>;
}

function mergeEvents(current: PublicJobEvent[], additions: PublicJobEvent[]) {
  const bySequence = new Map(current.map((item) => [item.sequence, item]));
  additions.forEach((item) => bySequence.set(item.sequence, item));
  return [...bySequence.values()].sort((a, b) => a.sequence - b.sequence);
}

function statusCopy(status: PublicJob["status"]) {
  return ({
    queued: { label: "等待开始", description: "任务已经保存，后台正在准备独立世界。" },
    running: { label: "正在推演", description: "不同主体正在依据各自掌握的信息行动。" },
    waiting_user: { label: "等你决定", description: "世界已经暂停在安全节点，等待你的选择。" },
    canceling: { label: "正在安全停止", description: "系统正在完成当前保存动作。" },
    completed: { label: "已经完成", description: "过程、结果和运行依据都已经保存。" },
    failed: { label: "这一阶段未完成", description: "已有内容仍在，可以从最近节点继续。" },
    canceled: { label: "已经取消", description: "任务在形成首个世界节点前停止。" },
    partial: { label: "部分完成", description: "已有过程和检查点可查看，也可以继续。" },
  } as const)[status];
}

function eventIcon(item: PublicJobEvent) {
  if (item.tone === "danger") return "!";
  if (item.tone === "warning") return "?";
  if (item.event_type === "stage.started") return "→";
  if (item.event_type === "job.completed") return "✓";
  return "·";
}

function stageActor(type: string) {
  return type.startsWith("job.") ? "任务系统" : type === "stage.started" ? "推演进程" : "InsideGov";
}

function duration(seconds: number) {
  const value = Math.max(0, Math.round(seconds));
  if (value < 60) return `${value} 秒`;
  return `${Math.floor(value / 60)} 分 ${value % 60} 秒`;
}

function timeOnly(timestamp: number) {
  return new Date(timestamp * 1000).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function readableError(error: unknown) {
  const raw = String(error);
  if (raw.includes("Failed to fetch")) return "暂时无法连接任务服务，系统会继续尝试恢复。";
  return raw.replace(/^Error:\s*/, "");
}
