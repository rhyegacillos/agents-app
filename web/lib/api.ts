export type TraderSummary = {
  name: string;
  lastname: string;
  model_name: string;
  balance: number;
  cash_balance: number;
  holdings_market_value: number;
  total_equity: number;
  total_portfolio_value: number;
  total_profit_loss: number;
  holdings_count: number;
  transactions_count: number;
};

export type TraderDetail = {
  summary: TraderSummary;
  account: {
    strategy?: string;
    balance?: number;
    cash_balance?: number;
    holdings_market_value?: number;
    total_equity?: number;
    total_portfolio_value?: number;
    total_profit_loss?: number;
    holdings: Record<string, number>;
    portfolio_value_time_series?: Array<[string, number]>;
    transactions: Array<{
      symbol: string;
      quantity: number;
      price: number;
      timestamp: string;
      rationale: string;
    }>;
  };
  logs: Array<{
    timestamp: string;
    type: string;
    message: string;
  }>;
};

export type SchedulerStatus = {
  running: boolean;
  pid: number | null;
  started_at: string | null;
  run_in_progress: boolean;
  last_run_started_at: string | null;
  last_run_ended_at: string | null;
  read_only_mode: boolean;
};

export type MarketStatus = {
  status: "open" | "closed" | "unknown";
  is_open: boolean | null;
  detail: string | null;
};

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/+$/, "");

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text || res.statusText}`);
  }

  return res.json() as Promise<T>;
}

export async function getTraders(): Promise<TraderSummary[]> {
  const data = await request<{ traders: TraderSummary[] }>("/api/traders");
  return data.traders;
}

export async function getTrader(name: string, logsLimit = 50): Promise<TraderDetail> {
  return request<TraderDetail>(`/api/traders/${encodeURIComponent(name)}?logs_limit=${logsLimit}`);
}

export async function getSchedulerStatus(): Promise<SchedulerStatus> {
  return request<SchedulerStatus>("/api/scheduler/status");
}

export async function getMarketStatus(): Promise<MarketStatus> {
  return request<MarketStatus>("/api/market/status");
}

export async function startScheduler(options?: {
  runEvenWhenMarketIsClosed?: boolean;
  runEveryNMinutes?: number;
}): Promise<SchedulerStatus> {
  const payload: Record<string, boolean | number> = {};
  if (options?.runEvenWhenMarketIsClosed !== undefined) {
    payload.run_even_when_market_is_closed = options.runEvenWhenMarketIsClosed;
  }
  if (options?.runEveryNMinutes !== undefined) {
    payload.run_every_n_minutes = options.runEveryNMinutes;
  }
  const body = Object.keys(payload).length > 0 ? JSON.stringify(payload) : undefined;
  return request<SchedulerStatus>("/api/scheduler/start", { method: "POST", body });
}

export async function stopScheduler(): Promise<SchedulerStatus> {
  return request<SchedulerStatus>("/api/scheduler/stop", { method: "POST" });
}

export async function resetTraders(): Promise<{ message: string }> {
  return request<{ message: string }>("/api/reset", { method: "POST" });
}
