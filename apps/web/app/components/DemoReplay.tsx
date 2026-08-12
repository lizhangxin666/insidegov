"use client";

import { useState } from "react";
import { API_BASE, api, type DemoBundle, type World } from "../lib/api";

type Props = {
  remember: (world: World) => void;
  refreshList: () => Promise<void>;
};

export function DemoReplay({ remember, refreshList }: Props) {
  const [bundle, setBundle] = useState<DemoBundle | null>(null);
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function runDemo() {
    setLoading(true);
    setError("");
    try {
      const result = await api.createDemo();
      setBundle(result);
      setStep(0);
      remember(result.baseline);
      await refreshList();
    } catch (caught) {
      setError(`演示生成失败：${String(caught)}`);
    } finally {
      setLoading(false);
    }
  }

  if (!bundle) {
    return <div className="demo-intro">
      <small>LIVE · FIVE-MINUTE EVIDENCE CHAIN</small>
      <h2>五分钟典型政企博弈回放</h2>
      <p>系统将现场运行合肥—蔚来校准世界：先推进共同历史，再从 Q3 复制基线与财政冲击分支，保持随机状态一致并运行至 Q16。</p>
      <ul>
        <li>不是前端预写剧情，每次都会生成新的世界 ID 和完整快照。</li>
        <li>展示企业表达、政府内部会商、独立产业基金、条件承诺与规则结算。</li>
        <li>确定性模式无需网络和模型 Key，比赛现场可稳定复现。</li>
      </ul>
      <button className="wide-button accent" data-testid="run-guided-demo" disabled={loading} onClick={() => void runDemo()}>
        {loading ? "正在运行 29 个世界季度…" : "现场生成并进入六步回放"}
      </button>
      {error && <p className="error-text">{error}</p>}
    </div>;
  }

  const current = bundle.replay.steps[step];
  const meeting = bundle.replay.internal_negotiation;
  const outward = bundle.replay.external_negotiation;
  const comparison = bundle.comparison.delta;

  return <div className="demo-replay" data-testid="guided-demo">
    <div className="replay-proof">
      <span>实时规则运行</span>
      <code>{bundle.baseline.id}</code>
      <code>{bundle.branch.id}</code>
      <b>Seed {bundle.seed} · 共同祖先 Q{bundle.common_ancestor_quarter}</b>
    </div>
    <ol className="replay-steps" aria-label="演示步骤">
      {bundle.replay.steps.map((item, index) => <li key={item.id} className={index === step ? "active" : index < step ? "done" : ""}>
        <button onClick={() => setStep(index)}><i>{index + 1}</i><span>{item.title}<small>Q{item.quarter}</small></span></button>
      </li>)}
    </ol>

    <section className="replay-stage">
      <header><small>STEP {step + 1} / 6</small><h3>{current.title}</h3></header>
      {current.id === "world" && <div className="replay-grid">
        <article><strong>公开资料</strong><p>合肥一般公共预算收入、企业资产与现金投入、12 万辆年产能、70 亿元历史股权投资均保留来源。</p></article>
        <article><strong>专家映射</strong><p>可调度财力默认取财政收入 25%；供应链、行政能力和信用指数均明确标为映射，不冒充公开事实。</p></article>
        <article><strong>模型假设</strong><p>就业容量和供应商进入窗口缺少企业级公开数据，报告中始终标注外推边界。</p></article>
      </div>}
      {current.id === "external" && <div className="evidence-stack">
        <p><b>企业表面诉求：</b>{outward.stated_need}</p>
        <p><b>政府追问：</b>{outward.government_questions.join("、")}</p>
        <p><b>认知更新：</b>{compact(outward.belief_before)} → {compact(outward.belief_after)}</p>
        <p><b>企业回应：</b>{outward.enterprise_response} · {outward.enterprise_rationale}</p>
      </div>}
      {current.id === "internal" && <>
        <div className="offer-chain">
          <article><small>招商局提案</small><strong>现金 {money(meeting.proposal_tools.subsidy)}</strong><strong>本级股权 {money(meeting.proposal_tools.equity)}</strong><span>联合基金申请 {money(meeting.proposal_tools.external_equity)}</span></article>
          <b>→</b>
          <article><small>财政局硬约束</small><strong>现金上限 {money(meeting.finance_tool_limits.subsidy)}</strong><strong>本级股权上限 {money(meeting.finance_tool_limits.equity)}</strong><span>{meeting.finance_approved ? "直接通过" : "要求重组"}</span></article>
          <b>→</b>
          <article><small>市领导协调后</small><strong>现金 {money(meeting.final_tools.subsidy)}</strong><strong>总股权 {money(meeting.final_tools.total_equity_support)}</strong><span>{meeting.payment_schedule.length} 个条件性支付节点</span></article>
        </div>
        <div className="private-audit">
          <h4>演示世界私有真值审计</h4>
          {bundle.replay.synthetic_private_audit.map((item) => <details key={item.audit_id}>
            <summary>{item.agent_id} · {item.provider} · {item.fallback ? "发生降级" : "原生执行"}</summary>
            <p><b>私有信息：</b>{compact(item.private_context_used)}</p>
            <p><b>当时观察：</b>{compact(item.observation)}</p>
            <p><b>认知建议：</b>{compact(item.llm_suggestion)}</p>
            <p><b>规则修正：</b>{compact(item.rule_adjustment)}</p>
            <p><b>最终执行：</b>{compact(item.executed_action)}</p>
          </details>)}
        </div>
      </>}
      {current.id === "contract" && <>
        <div className="fund-grid">{bundle.replay.funding_partners.map((fund) => <article key={fund.id}><small>{fund.source_level}</small><strong>{fund.name}</strong><p>独立风控阈值 {(fund.due_diligence_threshold * 100).toFixed(0)}%</p></article>)}</div>
        <div className="promise-table">{bundle.replay.promises.map((promise) => <div key={promise.id}><span>{promise.funding_source_id ? "联合基金股权" : toolName(promise.item)}</span><b>{money(promise.amount)}</b><span>Q{promise.due_quarter} · {promise.condition}</span><em className={promise.status}>{promise.status}</em></div>)}</div>
      </>}
      {current.id === "delivery" && <div className="event-chain">
        {bundle.replay.causal_events.slice(0, 12).map((event, index) => <article key={`${event.quarter}-${event.title}-${index}`}><time>Q{event.quarter}</time><div><strong>{event.title}</strong><p>{event.detail}</p></div></article>)}
      </div>}
      {current.id === "counterfactual" && <>
        <div className="comparison-cards">
          <article><small>基线 Q16</small><strong>{bundle.replay.baseline_outcome.cluster_size} 家集群</strong><span>{bundle.replay.baseline_outcome.total_employment.toLocaleString()} 个就业</span></article>
          <article className="warning"><small>Q4 财力减半</small><strong>{bundle.replay.branch_outcome.cluster_size} 家集群</strong><span>{bundle.replay.branch_outcome.total_employment.toLocaleString()} 个就业</span></article>
          <article><small>规则产生的差异</small><strong>{signed(comparison.cluster_size)} 家</strong><span>{signed(comparison.total_employment)} 个就业</span></article>
        </div>
        <p className="boundary">财力冲击 → 本级承诺延期 → 客观信用与企业感知下降 → 边缘供应商未达到进入门槛。差值是模型内部机制结果，不是现实政策因果效应。</p>
        <SensitivityTable bundle={bundle} />
      </>}
    </section>

    <footer className="replay-actions">
      <button disabled={step === 0} onClick={() => setStep((value) => value - 1)}>← 上一步</button>
      <button onClick={() => remember(bundle.baseline)}>打开基线世界</button>
      <button onClick={() => remember(bundle.branch)}>打开冲击分支</button>
      <a href={`${API_BASE}/worlds/${bundle.branch.id}/export`}>导出分支 JSON</a>
      {step < bundle.replay.steps.length - 1
        ? <button className="primary" onClick={() => setStep((value) => value + 1)}>下一步 →</button>
        : <button className="primary" onClick={() => void runDemo()}>重置并重新运行</button>}
    </footer>
  </div>;
}

function SensitivityTable({ bundle }: { bundle: DemoBundle }) {
  return <div className="sensitivity-table">
    <h4>财政空间 × 联合基金敏感性</h4>
    <div className="table-row header"><span>可调度财力</span><span>联合基金</span><span>总股权支持</span><span>与历史 70 亿差距</span><span>Q16 集群</span></div>
    {bundle.sensitivity.runs.map((run) => <div className="table-row" key={`${run.available_budget_share}-${run.joint_investment}`}>
      <span>{(run.available_budget_share * 100).toFixed(0)}%</span>
      <span>{run.joint_investment ? "开启" : "关闭"}</span>
      <b>{money(run.total_equity_support)}</b>
      <span>{money(run.historical_equity_gap)}</span>
      <span>{run.cluster_size} 家</span>
    </div>)}
  </div>;
}

function compact(value: unknown) {
  const text = JSON.stringify(value);
  return text.length > 420 ? `${text.slice(0, 417)}…` : text;
}

function money(value?: number) { return value == null ? "—" : `${value.toFixed(2)} 亿`; }
function signed(value?: number) { return value == null ? "—" : `${value > 0 ? "+" : ""}${value.toLocaleString()}`; }
function toolName(item: string) { return ({ subsidy: "现金补贴", equity: "本级股权", credit_support_cost: "信贷支持成本" } as Record<string, string>)[item] ?? item; }
