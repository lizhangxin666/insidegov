export const API_BASE = process.env.NEXT_PUBLIC_INSIDEGOV_API_URL ?? "http://localhost:8000";

export type Offer = {
  subsidy: number;
  equity: number;
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
  firms: Record<string, { id: string; name: string; operating: boolean; location: string | null }>;
  events: Array<{ quarter: number; kind: string; title: string; detail: string; severity: string }>;
  traces: Array<{
    id: string; actor_id: string; action: string; evidence: string[];
    constraints: string[]; outcome: string; expected_effects: Record<string, number>;
  }>;
  action_audits: AgentActionAudit[];
  history: Metric[];
  negotiations: Array<{
    id: string; quarter: number; city_id: string; proposal_cost: number;
    finance_limit: number; finance_approved: boolean; concerns: string[];
    resolution: string; final_cost: number; policy_mode: string;
    proposer_id: string; reviewer_id: string; coordinator_id: string;
    proposal_tools: Record<string, number>;
    finance_tool_limits: Record<string, number>;
    final_tools: Record<string, number>;
    payment_schedule: Array<{ item: string; amount: number; due_offset: number; condition: string }>;
    turns: Array<{ actor_id: string; act: string; summary: string; amount?: number; approved?: boolean }>;
  }>;
  external_negotiations: Array<{
    id: string; quarter: number; city_id: string; firm_id: string; protocol: string;
    stated_need: string; government_questions: string[];
    disclosed_components: Record<string, number>;
    belief_before: Record<string, number>; belief_after: Record<string, number>;
    belief_confidence: number; internal_negotiation_id: string;
    government_offer: Record<string, number>;
    enterprise_response: "accept" | "counter" | "terminate";
    counter_terms: Record<string, number>; enterprise_rationale: string;
    utility: number; minimum_utility: number; outcome: string;
  }>;
  selected_city_id: string | null;
  parent_id: string | null;
  policy_mode: string;
  model_name: string | null;
};

export type AgentActionAudit = {
  id: string;
  quarter: number;
  agent_id: string;
  action_type: string;
  observation: Record<string, unknown>;
  private_context_used: { redacted?: boolean; fields_used?: string[] } | Record<string, unknown>;
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
};

export type InterventionPlan = {
  id: string; source_text: string; effective_quarter: number; status: string;
  assumptions: string[]; promise_priority: string | null;
  changes: Array<{ target: string; operation: string; value: number; description: string }>;
};

export type Interview = {
  quarter: number; agent_id: string; question: string; answer: string;
  evidence_audit_ids: string[];
  knowledge_labels: {
    known_at_the_time: string[]; private_fields_used: string[];
    unknown_at_the_time: string[]; hindsight: string[]; hypothetical: boolean;
  };
};

export type CandidateWorld = {
  id: string; filename: string; content_excerpt: string; entities: string[];
  relations: Array<{ source: string; target: string; relation: string; evidence: string }>;
  missing_fields: string[]; status: string;
  parameters: Array<{
    id: string; target: string; evidence: string; suggested_value: number;
    final_value: number | null; confidence: number; provenance: string; status: string;
  }>;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json() as Promise<T>;
}

export const api = {
  capabilities: () => request<Capability>("/capabilities"),
  listWorlds: () => request<Array<Pick<World, "id" | "name" | "quarter" | "parent_id" | "policy_mode">>>("/worlds"),
  getWorld: (id: string) => request<World>(`/worlds/${id}`),
  createWorld: (seed: number, policyMode: string, modelName: string) => request<World>("/worlds", {
    method: "POST",
    body: JSON.stringify({ seed, policy_mode: policyMode, model_name: policyMode === "llm" ? modelName : null }),
  }),
  step: (id: string, quarters = 1) => request<World>(`/worlds/${id}/step`, {
    method: "POST", body: JSON.stringify({ quarters }),
  }),
  branch: (id: string) => request<World>(`/worlds/${id}/branches`, { method: "POST" }),
  branchFromHistory: (id: string, quarter: number) => request<World>(`/worlds/${id}/branches/from-history`, {
    method: "POST", body: JSON.stringify({ quarter }),
  }),
  createPair: (id: string, quarter: number) => request<{ baseline: World; branch: World; quarter: number }>(`/worlds/${id}/counterfactual-pairs`, {
    method: "POST", body: JSON.stringify({ quarter }),
  }),
  syncPair: (baselineId: string, branchId: string, quarters: number) => request<{ baseline: World; branch: World; comparison: { delta: Record<string, number> } }>("/experiments/sync-worlds", {
    method: "POST", body: JSON.stringify({ baseline_world_id: baselineId, branch_world_id: branchId, quarters }),
  }),
  intervene: (id: string, kind: string, target: string, value: number) => request<{ accepted: boolean }>(`/worlds/${id}/interventions`, {
    method: "POST", body: JSON.stringify({ kind, target, value }),
  }),
  audits: (id: string, quarter?: number, agentId?: string) => {
    const params = new URLSearchParams();
    if (quarter != null) params.set("quarter", String(quarter));
    if (agentId) params.set("agent_id", agentId);
    return request<AgentActionAudit[]>(`/worlds/${id}/audits?${params.toString()}`);
  },
  draftIntervention: (id: string, text: string) => request<InterventionPlan>(`/worlds/${id}/intervention-plans`, {
    method: "POST", body: JSON.stringify({ text }),
  }),
  confirmIntervention: (id: string, planId: string) => request<{ accepted: boolean; plan: InterventionPlan }>(`/worlds/${id}/intervention-plans/confirm`, {
    method: "POST", body: JSON.stringify({ plan_id: planId }),
  }),
  interview: (id: string, agentId: string, quarter: number, question: string) => request<Interview>(`/worlds/${id}/interviews`, {
    method: "POST", body: JSON.stringify({ agent_id: agentId, quarter, question }),
  }),
  createCandidate: (filename: string, content: string) => request<CandidateWorld>("/materials/candidates", {
    method: "POST", body: JSON.stringify({ filename, content }),
  }),
  confirmCandidate: (id: string, candidate: CandidateWorld) => request<World>(`/materials/candidates/${id}/confirm`, {
    method: "POST", body: JSON.stringify({
      parameters: candidate.parameters.map((item) => ({
        parameter_id: item.id, final_value: item.final_value ?? item.suggested_value,
        provenance: item.provenance,
      })),
      seed: 42,
    }),
  }),
};
