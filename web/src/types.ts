export interface Worker {
  id: string;
  role: "backtest" | "live";
  runtime_version: string;
  status: "online" | "degraded" | "offline";
  capacity: number;
  current_runs: number;
  last_heartbeat_at: string;
  metadata: Record<string, unknown>;
}

export interface Strategy {
  id: string;
  name: string;
  description?: string;
  owner?: string;
  created_at: string;
}

export interface BacktestRun {
  id: string;
  strategy_version_id: string;
  status: string;
  dataset: string;
  worker_id?: string;
  result: {
    metrics?: Record<string, number>;
  };
  error?: string;
  created_at: string;
}

export interface Deployment {
  id: string;
  name: string;
  worker_id: string;
  desired_state: string;
  actual_state: string;
  desired_revision: number;
  generation: number;
  created_at: string;
}

export interface AuditEvent {
  id: string;
  actor: string;
  action: string;
  object_type: string;
  object_id: string;
  created_at: string;
}

export interface Summary {
  workers: { total: number; online: number; degraded: number; offline: number };
  strategies: { total: number };
  backtests: { total: number; active: number; succeeded: number; failed: number };
  deployments: { total: number; running: number; failed: number };
}
