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
  history: Metric[];
  negotiations: Array<{
    id: string; quarter: number; city_id: string; proposal_cost: number;
    finance_limit: number; finance_approved: boolean; concerns: string[];
    resolution: string; final_cost: number; policy_mode: string;
  }>;
  selected_city_id: string | null;
  parent_id: string | null;
  policy_mode: string;
  model_name: string | null;
};

export type Capability = {
  persistence: boolean;
  llm_available: boolean;
  models: string[];
  default_model: string;
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
  intervene: (id: string, kind: string, target: string, value: number) => request<{ accepted: boolean }>(`/worlds/${id}/interventions`, {
    method: "POST", body: JSON.stringify({ kind, target, value }),
  }),
};
