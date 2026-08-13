export const API_BASE =
  process.env.NEXT_PUBLIC_INSIDEGOV_API_URL ?? "http://localhost:8000";

export type Offer = {
  subsidy: number;
  equity: number;
  external_equity: number;
  fund_allocations: Record<string, number>;
  land_discount: number;
  credit_support: number;
};

export type City = {
  id: string;
  name: string;
  available_budget: number;
  industrial_land: number;
  supply_chain: number;
  objective_credibility: number;
  active_offer: Offer | null;
  landed_firms: string[];
};

export type Metric = {
  quarter: number;
  phase: string;
  total_employment: number;
  total_tax_revenue: number;
  total_committed_expenditure: number;
  average_credibility: number;
  cluster_size: number;
  capacity: number;
  demand: number;
  utilization: number;
  market_price: number;
};

export type World = {
  id: string;
  name: string;
  seed: number;
  quarter: number;
  phase: string;
  cities: Record<string, City>;
  firms: Record<
    string,
    { id: string; name: string; operating: boolean; location: string | null }
  >;
  investment_funds: Record<
    string,
    {
      id: string;
      name: string;
      city_id: string;
      source_level: string;
      available_capital: number;
      committed_capital: number;
      risk_tolerance: number;
      due_diligence_threshold: number;
    }
  >;
  promises: Array<{
    id: string;
    item: string;
    amount: number;
    due_quarter: number;
    condition: string;
    status: string;
    paid_amount: number;
    delayed_quarters: number;
    funding_source_id: string | null;
  }>;
  events: Array<{
    quarter: number;
    kind: string;
    title: string;
    detail: string;
    severity: string;
  }>;
  traces: Array<{
    id: string;
    actor_id: string;
    action: string;
    evidence: string[];
    constraints: string[];
    outcome: string;
    expected_effects: Record<string, number>;
  }>;
  action_audits: AgentActionAudit[];
  organization_actions: OrganizationAction[];
  organization_plans: OrganizationPlan[];
  open_action_proposals: OpenActionProposal[];
  opportunity_windows: OpportunityWindow[];
  organization_learning: Record<string, OrganizationLearning>;
  organization_processes: Record<
    string,
    {
      city_id: string;
      agenda_priority: number;
      procedural_completeness: number;
      coalition_support: number;
      legitimacy: number;
      risk_posture: string;
      finance_preconsulted: boolean;
      legal_reviewed: boolean;
      collective_deliberated: boolean;
      pilot_authorized: boolean;
      relationships: Record<string, number>;
      action_sequence: string[];
      formal_status: string;
      return_count: number;
      last_transition: string;
      last_transition_quarter: number;
      paused_reason: string | null;
      attention_budget: number;
    }
  >;
  history: Metric[];
  negotiations: Array<{
    id: string;
    quarter: number;
    city_id: string;
    proposal_cost: number;
    finance_limit: number;
    finance_approved: boolean;
    concerns: string[];
    resolution: string;
    final_cost: number;
    policy_mode: string;
    proposer_id: string;
    reviewer_id: string;
    coordinator_id: string;
    proposal_tools: Record<string, number>;
    finance_tool_limits: Record<string, number>;
    final_tools: Record<string, number>;
    payment_schedule: Array<{
      item: string;
      amount: number;
      due_offset: number;
      condition: string;
      funding_source_id?: string | null;
    }>;
    turns: Array<{
      actor_id: string;
      act: string;
      summary: string;
      amount?: number;
      approved?: boolean;
    }>;
  }>;
  external_negotiations: Array<{
    id: string;
    quarter: number;
    city_id: string;
    firm_id: string;
    protocol: string;
    stated_need: string;
    government_questions: string[];
    disclosed_components: Record<string, number>;
    belief_before: Record<string, number>;
    belief_after: Record<string, number>;
    belief_confidence: number;
    internal_negotiation_id: string;
    government_offer: Record<string, number>;
    enterprise_response: "accept" | "counter" | "terminate";
    counter_terms: Record<string, number>;
    enterprise_rationale: string;
    utility: number;
    minimum_utility: number;
    outcome: string;
  }>;
  selected_city_id: string | null;
  recruitment_status: string;
  negotiation_round_limit: number;
  parent_id: string | null;
  policy_mode: string;
  process_mode: "formal" | "informal" | "hybrid";
  model_name: string | null;
};

export type OrganizationAction = {
  id: string;
  quarter: number;
  city_id: string;
  actor_id: string;
  actor_role: string;
  action_id: string;
  action_name: string;
  arena: "formal" | "informal" | "control" | "initiative" | "procedure";
  process_mode: string;
  candidates: string[];
  observations: Record<string, number>;
  rationale: string;
  effects: Record<string, number>;
  required: boolean;
  authorized: boolean;
  blocked_reason: string | null;
  evidence_ids: string[];
  selection_provider: string;
  selection_rationale: string;
  fallback: boolean;
  stage: string;
  sequence: number;
  decision: string;
  target_actor_id: string | null;
  urgency: number;
  reflection: string;
  plan_id: string | null;
  plan_node_id: string | null;
  deviation_reason: string | null;
  open_action_proposal_id: string | null;
};

export type OrganizationPlan = {
  id: string;
  city_id: string;
  actor_id: string;
  created_quarter: number;
  horizon_quarter: number;
  objective: string;
  alternatives: Array<{
    id: string; name: string; approach: string; benefits: string[]; risks: string[]; score: number;
  }>;
  selected_strategy: string;
  nodes: Array<{
    id: string; title: string; action_id: string; earliest_quarter: number; latest_quarter: number;
    preconditions: string[]; on_success: string | null; on_failure: string | null;
    expected_effects: Record<string, number>; status: string; executed_quarter: number | null;
    actual_action_id: string | null; deviation_reason: string | null;
  }>;
  assumptions: string[];
  rationale: string;
  status: string;
  provider: string;
  fallback: boolean;
  review_history: Array<Record<string, unknown>>;
};

export type OpenActionProposal = {
  id: string; quarter: number; city_id: string; actor_id: string; title: string;
  mechanism: string; target_actor_id: string | null;
  requested_effects: Record<string, number>; resource_request: Record<string, number>;
  rationale: string; status: string; validation_reason: string;
  executed_effects: Record<string, number>; provider: string; fallback: boolean;
};

export type OpportunityWindow = {
  id: string; city_id: string | null; kind: string; title: string;
  start_quarter: number; end_quarter: number; magnitude: number;
  source: string; trigger: string; effects: Record<string, number>;
  observed_by: string[]; status: string; applied: boolean;
};

export type OrganizationLearning = {
  agent_id: string; trust_by_actor: Record<string, number>;
  firm_type_beliefs: Record<string, number>; action_attempts: Record<string, number>;
  action_successes: Record<string, number>; strategy_preferences: Record<string, number>;
  routines: Record<string, number>; veto_count: number; successful_coordination_count: number;
  leadership_generation: number; inherited_memory_ratio: number;
  lessons: string[]; transferable_lessons: string[];
};

export type AgentActionAudit = {
  id: string;
  quarter: number;
  agent_id: string;
  action_type: string;
  observation: Record<string, unknown>;
  private_context_used:
    { redacted?: boolean; fields_used?: string[] } | Record<string, unknown>;
  retrieved_memories: string[];
  llm_suggestion: Record<string, unknown>;
  rule_adjustment: Record<string, unknown>;
  executed_action: Record<string, unknown>;
  rationale: string;
  reflection: string;
  provider: string;
  fallback: boolean;
  diagnostics: Array<Record<string, unknown>>;
  outcome: string;
};

export type Capability = {
  persistence: boolean;
  llm_available: boolean;
  models: string[];
  default_model: string;
  process_modes?: string[];
};

export type InterventionPlan = {
  id: string;
  source_text: string;
  effective_quarter: number;
  status: string;
  assumptions: string[];
  promise_priority: string | null;
  changes: Array<{
    target: string;
    operation: string;
    value: number;
    description: string;
  }>;
};

export type Interview = {
  quarter: number;
  agent_id: string;
  question: string;
  answer: string;
  evidence_audit_ids: string[];
  knowledge_labels: {
    known_at_the_time: string[];
    private_fields_used: string[];
    unknown_at_the_time: string[];
    hindsight: string[];
    hypothetical: boolean;
  };
};

export type CandidateWorld = {
  id: string;
  filename: string;
  content_excerpt: string;
  entities: string[];
  relations: Array<{
    source: string;
    target: string;
    relation: string;
    evidence: string;
  }>;
  missing_fields: string[];
  status: string;
  parameters: Array<{
    id: string;
    target: string;
    evidence: string;
    suggested_value: number;
    final_value: number | null;
    confidence: number;
    provenance: string;
    status: string;
  }>;
};

export type DemoBundle = {
  schema_version: string;
  generated_at: string;
  source: string;
  seed: number;
  common_ancestor_quarter: number;
  intervention: {
    quarter: number;
    target: string;
    operation: string;
    value: number;
  };
  baseline: World;
  branch: World;
  comparison: {
    baseline_world_id: string;
    branch_world_id: string;
    delta: Record<string, number>;
  };
  replay: {
    selected_city_id: string;
    selected_city_name: string;
    external_negotiation: World["external_negotiations"][number];
    internal_negotiation: World["negotiations"][number];
    synthetic_private_audit: Array<{
      audit_id: string;
      agent_id: string;
      private_context_used: Record<string, unknown>;
      observation: Record<string, unknown>;
      llm_suggestion: Record<string, unknown>;
      rule_adjustment: Record<string, unknown>;
      executed_action: Record<string, unknown>;
      rationale: string;
      reflection: string;
      provider: string;
      fallback: boolean;
    }>;
    funding_partners: Array<World["investment_funds"][string]>;
    promises: World["promises"];
    baseline_outcome: Metric;
    branch_outcome: Metric;
    causal_events: World["events"];
    steps: Array<{ id: string; title: string; quarter: number }>;
  };
  sensitivity: HefeiSensitivity;
};

export type HefeiSensitivity = {
  case: string;
  seed: number;
  quarters: number;
  historical_equity_investment: number;
  budget_shares: number[];
  interpretation_boundary: string;
  runs: Array<{
    available_budget_share: number;
    joint_investment: boolean;
    selected_city: string | null;
    municipal_equity: number;
    external_equity: number;
    total_equity_support: number;
    historical_equity_gap: number;
    fulfilled_promises: number;
    cluster_size: number;
    total_employment: number;
    average_credibility: number;
  }>;
};

export type ExperimentReportSummary = {
  id: string;
  title: string;
  kind: string;
  source: string;
  generated_at: string | null;
  strategy_runs: number;
  ablation_runs: number;
  failures: number;
  drilldown_available: boolean;
};

export type ExperimentRun = {
  strategy: string;
  seed: number;
  successful: boolean;
  selected_city: string | null;
  fulfilled_promises: number;
  total_employment: number;
  total_committed_expenditure: number;
  average_credibility: number;
  cluster_size: number;
  utilization: number;
  world_id: string;
  world_available: boolean;
};

export type ExperimentMetricSummary = {
  id?: string;
  name?: string;
  strategy?: string;
  mechanism?: string;
  attempted?: number;
  successful?: number;
  success_rate?: number;
  metrics?: Record<string, { mean: number; variance: number; n: number }>;
  employment?: number;
  employment_variance?: number;
  cluster?: number;
  fulfilled_promises?: number;
  seeds?: number;
};

export type ExperimentReport = {
  report_id: string;
  generated_at?: string;
  report_summary: Partial<ExperimentReportSummary>;
  configuration: Record<string, unknown>;
  strategy_summary: ExperimentMetricSummary[];
  ablation_summary: ExperimentMetricSummary[];
  strategy_runs: ExperimentRun[];
  ablation_runs: ExperimentRun[];
  failure_cases: Array<{
    strategy: string;
    seed: number;
    stage: string;
    reason: string;
  }>;
  llm_quality?: Array<Record<string, unknown>>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok)
    throw new Error(`${response.status} ${await response.text()}`);
  return response.json() as Promise<T>;
}

export const api = {
  capabilities: () => request<Capability>("/capabilities"),
  listWorlds: () =>
    request<
      Array<
        Pick<World, "id" | "name" | "quarter" | "parent_id" | "policy_mode">
      >
    >("/worlds"),
  getWorld: (id: string) => request<World>(`/worlds/${id}`),
  createWorld: (
    seed: number,
    policyMode: string,
    modelName: string,
    processMode = "hybrid",
  ) =>
    request<World>("/worlds", {
      method: "POST",
      body: JSON.stringify({
        seed,
        policy_mode: policyMode,
        model_name: policyMode === "llm" ? modelName : null,
        process_mode: processMode,
      }),
    }),
  step: (id: string, quarters = 1) =>
    request<World>(`/worlds/${id}/step`, {
      method: "POST",
      body: JSON.stringify({ quarters }),
    }),
  branch: (id: string) =>
    request<World>(`/worlds/${id}/branches`, { method: "POST" }),
  branchFromHistory: (id: string, quarter: number) =>
    request<World>(`/worlds/${id}/branches/from-history`, {
      method: "POST",
      body: JSON.stringify({ quarter }),
    }),
  createPair: (id: string, quarter: number) =>
    request<{ baseline: World; branch: World; quarter: number }>(
      `/worlds/${id}/counterfactual-pairs`,
      {
        method: "POST",
        body: JSON.stringify({ quarter }),
      },
    ),
  syncPair: (baselineId: string, branchId: string, quarters: number) =>
    request<{
      baseline: World;
      branch: World;
      comparison: { delta: Record<string, number> };
    }>("/experiments/sync-worlds", {
      method: "POST",
      body: JSON.stringify({
        baseline_world_id: baselineId,
        branch_world_id: branchId,
        quarters,
      }),
    }),
  intervene: (id: string, kind: string, target: string, value: number) =>
    request<{ accepted: boolean }>(`/worlds/${id}/interventions`, {
      method: "POST",
      body: JSON.stringify({ kind, target, value }),
    }),
  audits: (id: string, quarter?: number, agentId?: string) => {
    const params = new URLSearchParams();
    if (quarter != null) params.set("quarter", String(quarter));
    if (agentId) params.set("agent_id", agentId);
    return request<AgentActionAudit[]>(
      `/worlds/${id}/audits?${params.toString()}`,
    );
  },
  draftIntervention: (id: string, text: string) =>
    request<InterventionPlan>(`/worlds/${id}/intervention-plans`, {
      method: "POST",
      body: JSON.stringify({ text }),
    }),
  confirmIntervention: (id: string, planId: string) =>
    request<{ accepted: boolean; plan: InterventionPlan }>(
      `/worlds/${id}/intervention-plans/confirm`,
      {
        method: "POST",
        body: JSON.stringify({ plan_id: planId }),
      },
    ),
  interview: (id: string, agentId: string, quarter: number, question: string) =>
    request<Interview>(`/worlds/${id}/interviews`, {
      method: "POST",
      body: JSON.stringify({ agent_id: agentId, quarter, question }),
    }),
  createCandidate: (filename: string, content: string) =>
    request<CandidateWorld>("/materials/candidates", {
      method: "POST",
      body: JSON.stringify({ filename, content }),
    }),
  confirmCandidate: (id: string, candidate: CandidateWorld) =>
    request<World>(`/materials/candidates/${id}/confirm`, {
      method: "POST",
      body: JSON.stringify({
        parameters: candidate.parameters.map((item) => ({
          parameter_id: item.id,
          final_value: item.final_value ?? item.suggested_value,
          provenance: item.provenance,
        })),
        seed: 42,
      }),
    }),
  createDemo: (seed = 42, fiscalMultiplier = 0.5) =>
    request<DemoBundle>("/demos/hefei-nio", {
      method: "POST",
      body: JSON.stringify({ seed, fiscal_multiplier: fiscalMultiplier }),
    }),
  hefeiSensitivity: (seed = 42) =>
    request<HefeiSensitivity>(`/cases/hefei-nio/sensitivity?seed=${seed}`),
  listExperimentReports: () =>
    request<ExperimentReportSummary[]>("/experiment-reports"),
  getExperimentReport: (id: string) =>
    request<ExperimentReport>(`/experiment-reports/${id}`),
  getExperimentWorld: (reportId: string, worldId: string) =>
    request<World>(`/experiment-reports/${reportId}/worlds/${worldId}`),
};
