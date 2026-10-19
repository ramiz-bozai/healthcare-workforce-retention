export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      detail = await res.text();
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const parsed = await res.json();
      detail = parsed.detail || JSON.stringify(parsed);
    } catch {
      detail = await res.text();
    }
    throw new Error(detail);
  }
  return res.json();
}

export type Card = { label: string; column: string; value: string; cite: string };

export type Overview = {
  as_of: string;
  high_risk_percentile: number;
  disclaimer: string;
  note: string;
  cards: Card[];
  summary: Record<string, unknown>;
  preview_risk: Record<string, unknown>[];
  preview_units: Record<string, unknown>[];
  genie_live: boolean;
  model_serving_live: boolean;
  mode: string;
  serving: string;
};

export type SqlBlock = { title?: string | null; description?: string | null; sql: string };

export type AskTurn = {
  question: string;
  answer: string;
  intent: string;
  tools_called: string[];
  valid: boolean;
  unmatched: string[];
  mode: string;
  genie_live: boolean;
  model_serving_live: boolean;
  conversation_id?: string | null;
  sql?: SqlBlock[];
  rows?: Record<string, unknown>[];
  suggested?: string[];
  error?: string | null;
};
