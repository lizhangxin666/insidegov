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
  distressed_firms: number;
  rescued_firms: number;
  exited_firms: number;
  zombie_firms: number;
  rescue_spending: number;
  imitation_capacity: number;
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
  imitation_policy: string;
  rescue_policy: string;
  imitation_decisions: DynamicImitationDecision[];
  rescue_decisions: DynamicRescueDecision[];
  selected_city_id: string | null;
  recruitment_status: string;
  negotiation_round_limit: number;
  parent_id: string | null;
  policy_mode: string;
  process_mode: "formal" | "informal" | "hybrid";
  model_name: string | null;
};

export type DynamicImitationDecision = {
  id: string;
  quarter: number;
  city_id: string;
  source_city_id: string;
  observed_signal: Record<string, number>;
  strategy: string;
  requested_cost: number;
  approved_cost: number;
  added_capacity: number;
  added_jobs: number;
  created_firm_id: string | null;
  rationale: string;
  provider: string;
  turns: Array<Record<string, unknown>>;
};

export type DynamicRescueDecision = {
  id: string;
  quarter: number;
  city_id: string;
  firm_id: string;
  requested_amount: number;
  finance_limit: number;
  decision: string;
  approved_amount: number;
  conditional: boolean;
  capacity_before: number;
  capacity_after: number;
  jobs_before: number;
  jobs_after: number;
  rationale: string;
  provider: string;
  turns: Array<{ actor_id?: string; act?: string; summary?: string }>;
};

export type DynamicCompetitionReport = {
  schema_version: string;
  seed: number;
  quarters: number;
  agent_runtime: {
    mode: string;
    model_name: string | null;
    providers: string[];
    audited_agent_decisions: number;
    fallback_count: number;
    fixed_for_public_experience: boolean;
  };
  common_conditions: {
    imitation_policy: string;
    demand_shock_quarter: number;
    demand_shock: number;
    changed_variable: string;
  };
  causal_chain: string[];
  variants: Array<{
    id: string;
    name: string;
    description: string;
    final: Metric & {
      available_budget: number;
      imitation_projects: number;
    };
    trajectory: Array<{
      quarter: number;
      employment: number;
      capacity: number;
      demand: number;
      utilization: number;
      exited_firms: number;
      zombie_firms: number;
      rescue_spending: number;
      imitation_capacity: number;
    }>;
    imitation_decisions: DynamicImitationDecision[];
    rescue_decisions: DynamicRescueDecision[];
    key_events: Array<Record<string, unknown>>;
  }>;
  headline_comparison: Record<string, string>;
  interpretation_boundary: string;
};

export type DueDiligenceEvidence = {
  id: string;
  round: number;
  requested_by: string;
  action_id: string;
  dimension: string;
  source_type: string;
  observed_quality: number;
  reliability: number;
  claim_value: number;
  conflict: number;
  cost: number;
  elapsed_days: number;
  summary: string;
};

export type DueDiligenceCase = {
  id: string;
  firm_id: string;
  firm_name: string;
  program: string;
  prior_failure_probability: number;
  estimated_failure_probability: number;
  uncertainty: number;
  decision: "approve" | "conditional_pilot" | "defer" | "reject";
  rationale: string;
  rounds: number;
  diligence_cost: number;
  elapsed_days: number;
  evidence: DueDiligenceEvidence[];
  agent_turns: Array<Record<string, unknown>>;
  actual_failure_probability: number;
  actual_outcome: "failed" | "succeeded";
  avoided_fiscal_loss: number;
  realized_fiscal_loss: number;
  missed_opportunity: number;
  initial_trust: number;
  decision_used_hidden_label: false;
};

export type DueDiligenceReport = {
  schema_version: string;
  research_question: string;
  agent_runtime: {
    mode: string;
    model_name: string | null;
    providers: string[];
    audited_agent_decisions: number;
    fallback_count: number;
    fixed_for_public_experience: boolean;
  };
  configuration: {
    seeds: number[];
    programs: string[];
    thresholds: number[];
    mode: string;
    model_name: string | null;
    hidden_label_visible_to_agents: false;
  };
  program_summary: Array<{
    id: string;
    name: string;
    description: string;
    runs: number;
    metrics: Record<string, { mean: number; variance: number }>;
    action_counts: Record<string, number>;
  }>;
  program_runs: Array<{
    program: string;
    seed: number;
    precision: number;
    recall: number;
    specificity: number;
    brier_score: number;
    cases: DueDiligenceCase[];
  }>;
  threshold_curve: Array<{
    threshold: number;
    true_positive_rate: number;
    false_positive_rate: number;
    precision: number;
    specificity: number;
    realized_fiscal_loss: number;
    missed_opportunity: number;
  }>;
  decision_definitions: Record<string, string>;
  metric_definitions: Record<string, string>;
  interpretation_boundary: string;
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

export type StepJob = {
  id: string;
  world_id: string;
  status: "queued" | "running" | "completed" | "failed";
  quarters: number;
  completed_quarters: number;
  current_quarter_index: number;
  start_quarter: number;
  result_quarter?: number;
  world_quarter: number;
  phase: string;
  agent_audits: number;
  organization_actions: number;
  events: number;
  elapsed_seconds: number;
  message: string;
  error: string | null;
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

export type ConversationMechanism = {
  id: string;
  name: string;
  description: string;
  dimensions: {
    mutual_confirmation: boolean;
    pre_commitment_consultation: boolean;
    conditional_commitment: boolean;
  };
  enabled: string[];
  disabled: string[];
};

export type ConversationExperience = {
  schema_version: string;
  world_id: string;
  authority_engine: string;
  agent_runtime: PublicAgentRuntime;
  mechanism: ConversationMechanism;
  compiled_event: {
    title: string;
    source_text: string;
    initially_informed_agent_ids: string[];
    initially_uninformed_agent_ids: string[];
    observable_signals: string[];
    authoritative_change: Record<string, string | number>;
    parameter_source: string;
  };
  focus_firm: { id: string; name: string };
  result: {
    decision: string;
    estimated_failure_probability: number;
    uncertainty: number;
    evidence_count: number;
    elapsed_days: number;
    negotiation_outcome: string;
    fail_reason: string | null;
    understanding_gap_before: number;
    understanding_gap_after: number;
    policy_fit: number;
    government_cost: number;
  };
  timeline: Array<{
    round: number;
    actor_id: string;
    action: string;
    detail: string;
    kind: string;
  }>;
  evidence: Array<{
    id: string;
    dimension: string;
    source_type: string;
    observed_quality: number;
    reliability: number;
    claim_value: number;
    conflict: number;
    summary: string;
  }>;
  audit_count: number;
  boundary: string;
};

export type StoryManifest = {
  id: string;
  title: string;
  subtitle: string;
  roles: Array<{ id: string; name: string; motive: string }>;
  rules: string[];
};

export type StoryView = {
  session_id: string;
  source_world_id: string;
  world_id: string;
  authority_engine: string;
  agent_runtime: PublicAgentRuntime;
  turn: number;
  quarter: number;
  phase: string;
  scene_title: string;
  player: {
    id: string;
    name: string;
    role: string;
    goals: string[];
    private_facts: Array<{ key: string; value: string | number | boolean }>;
    last_reflection: string;
  };
  signals: Array<{ label: string; level: string }>;
  narrative: string[];
  recent_events: Array<{ title: string; detail: string; severity: string }>;
  available_actions: Array<{
    id: string;
    name: string;
    arena: string;
    rationale: string;
    evidence_ids: string[];
  }>;
  receipt: null | {
    directive_id: string;
    requested_action: string;
    status: string;
    executed_action: null | {
      action_name: string;
      blocked_reason: string | null;
      selection_rationale: string;
      effects: Record<string, number>;
    };
    new_agent_audits: number;
    new_events: Array<{ title: string; detail: string }>;
    rule_statement: string;
  };
  world_summary: {
    selected_city: string | null;
    recruitment_status: string;
    organization_actions: number;
    agent_audits: number;
    events: number;
  };
  boundary: string;
};

export type PublicAgentRuntime = {
  mode: "llm";
  model_name: string;
  providers: string[];
  audited_agent_decisions: number;
  fallback_count: number;
  fixed_for_public_experience: true;
};

export type PublicJobStatus = "queued" | "running" | "waiting_user" | "canceling" | "completed" | "failed" | "canceled" | "partial";

export type PublicJob = {
  id: string;
  scene: "coordination" | "diligence" | "dynamic_competition" | "conversation" | "story_turn";
  title: string;
  status: PublicJobStatus;
  stage_index: number;
  stage_label: string;
  message: string;
  config: Record<string, unknown>;
  checkpoint: null | { world_id?: string; quarter?: number; snapshot?: string; note?: string };
  error: string | null;
  model_name: string;
  attempt: number;
  parent_job_id: string | null;
  created_at: number;
  started_at: number | null;
  updated_at: number;
  finished_at: number | null;
  heartbeat_at: number | null;
  event_count: number;
  stages: string[];
  elapsed_seconds: number;
};

export type PublicJobEvent = {
  job_id: string;
  sequence: number;
  event_type: string;
  stage_index: number;
  actor: string | null;
  title: string;
  detail: string;
  tone: "neutral" | "success" | "warning" | "danger" | string;
  payload: Record<string, unknown>;
  created_at: number;
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
  startStepJob: (id: string, quarters = 1) =>
    request<StepJob>(`/worlds/${id}/step-jobs`, {
      method: "POST",
      body: JSON.stringify({ quarters }),
    }),
  getStepJob: (jobId: string) => request<StepJob>(`/step-jobs/${jobId}`),
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
  dynamicCompetition: (seed = 42, quarters = 24, demandShock = -0.42) =>
    request<DynamicCompetitionReport>(
      `/experiments/dynamic-competition?seed=${seed}&quarters=${quarters}&demand_shock=${demandShock}`,
    ),
  dueDiligence: () =>
    request<DueDiligenceReport>("/experiments/due-diligence"),
  createPublicJob: (scene: PublicJob["scene"], config: Record<string, unknown>) =>
    request<PublicJob>("/experience/jobs", {
      method: "POST",
      body: JSON.stringify({ scene, config }),
    }),
  listPublicJobs: (limit = 20) =>
    request<PublicJob[]>(`/experience/jobs?limit=${limit}`),
  getPublicJob: (jobId: string) =>
    request<PublicJob>(`/experience/jobs/${jobId}`),
  getPublicJobEvents: (jobId: string, after = 0) =>
    request<PublicJobEvent[]>(`/experience/jobs/${jobId}/events?after=${after}`),
  getPublicJobResult: <T = unknown>(jobId: string) =>
    request<T>(`/experience/jobs/${jobId}/result`),
  cancelPublicJob: (jobId: string) =>
    request<PublicJob>(`/experience/jobs/${jobId}/cancel`, { method: "POST" }),
  retryPublicJob: (jobId: string) =>
    request<PublicJob>(`/experience/jobs/${jobId}/retry`, { method: "POST" }),
  publicCoordination: (processMode: "formal" | "informal" | "hybrid") =>
    request<World>("/experience/coordination", {
      method: "POST",
      body: JSON.stringify({ process_mode: processMode, seed: 42 }),
    }),
  publicDueDiligence: (program: string) =>
    request<DueDiligenceReport>("/experience/due-diligence", {
      method: "POST",
      body: JSON.stringify({ program, seed: 42 }),
    }),
  publicDynamicCompetition: (policy: string) =>
    request<DynamicCompetitionReport>("/experience/dynamic-competition", {
      method: "POST",
      body: JSON.stringify({ policy, seed: 42, quarters: 16 }),
    }),
  conversationMechanisms: () =>
    request<ConversationMechanism[]>("/experience/conversation-mechanisms"),
  runConversationExperience: (
    mechanismId: string,
    eventText: string,
  ) =>
    request<ConversationExperience>("/experience/conversations", {
      method: "POST",
      body: JSON.stringify({
        mechanism_id: mechanismId,
        event_text: eventText,
        seed: 42,
      }),
    }),
  storyManifest: () => request<StoryManifest>("/experience/story-manifest"),
  startStory: (playerAgentId: string) =>
    request<StoryView>("/experience/story-sessions", {
      method: "POST",
      body: JSON.stringify({
        player_agent_id: playerAgentId,
        seed: 42,
      }),
    }),
  playStoryTurn: (sessionId: string, actionId: string, statement: string) =>
    request<StoryView>(`/experience/story-sessions/${sessionId}/actions`, {
      method: "POST",
      body: JSON.stringify({ action_id: actionId, statement }),
    }),
  listExperimentReports: () =>
    request<ExperimentReportSummary[]>("/experiment-reports"),
  getExperimentReport: (id: string) =>
    request<ExperimentReport>(`/experiment-reports/${id}`),
  getExperimentWorld: (reportId: string, worldId: string) =>
    request<World>(`/experiment-reports/${reportId}/worlds/${worldId}`),
};
