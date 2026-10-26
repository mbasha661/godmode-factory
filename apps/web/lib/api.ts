import { getSupabase } from "./supabase";
// @ts-ignore - plain-JS helper so node --test can cover it without a TS toolchain
import { executeWithRetry } from "./startRun.mjs";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function authHeaders(): Promise<Record<string, string>> {
  const { data } = await getSupabase().auth.getSession();
  const token = data.session?.access_token;
  if (!token) throw new Error("not signed in");
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = await authHeaders();
  const res = await fetch(`${API_URL}${path}`, { ...init, headers: { ...headers, ...(init.headers || {}) } });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const msg = body?.detail?.message || `request failed (${res.status})`;
    throw new Error(msg);
  }
  return body as T;
}

export type Project = {
  id: string; name: string; description: string; project_type: string;
  status: string; created_at: string; updated_at: string;
};

export const api = {
  listProjects: () => request<Project[]>("/api/projects"),
  getProject: (id: string) => request<Project>(`/api/projects/${id}`),
  createProject: (p: { name: string; description: string; project_type: string }) =>
    request<Project>("/api/projects", { method: "POST", body: JSON.stringify(p) }),
  deleteProject: (id: string) => request<void>(`/api/projects/${id}`, { method: "DELETE" }),
  systemStatus: () => request<Record<string, unknown>>("/api/system/status"),
  createRun: (projectId: string) =>
    request<{ run: WorkflowRun; tasks: RunTask[] }>(`/api/projects/${projectId}/runs`, { method: "POST" }),
  getRun: (runId: string) => request<RunDetail>(`/api/runs/${runId}`),
  stepRun: (runId: string) => request<WorkflowRun>(`/api/runs/${runId}/step`, { method: "POST" }),
  executeRun: (runId: string) =>
    request<{ status: string }>(`/api/runs/${runId}/execute`, { method: "POST" }),
  // Retries transient execute failures (cold starts, deploy cutovers) so a
  // created run is never orphaned in "pending". Safe because execute is
  // idempotent server-side ("already_executing" is success).
  executeRunWithRetry: (runId: string): Promise<{ status: string }> =>
    executeWithRetry(() => api.executeRun(runId)),
  cancelRun: (runId: string) => request<WorkflowRun>(`/api/runs/${runId}/cancel`, { method: "POST" }),
};

export type RunTask = {
  id: string; agent_role: string; kind: string; status: string;
  attempts: number; output?: Record<string, unknown> | null;
};
export type RunEvent = {
  id: string; event_type: string; message: string; level: string; created_at: string;
};
export type WorkflowRun = {
  id: string; status: string; current_task_id: string | null;
  error_summary: string | null; created_at: string; finished_at: string | null;
};
export type RunDetail = { run: WorkflowRun; tasks: RunTask[]; events: RunEvent[] };

