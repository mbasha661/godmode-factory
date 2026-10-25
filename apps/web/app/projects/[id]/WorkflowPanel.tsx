"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, RunDetail } from "@/lib/api";

const STATUS_COLOR: Record<string, string> = {
  succeeded: "#16a34a", failed: "#dc2626", running: "#2563eb",
  ready: "#7c3aed", pending: "#6b7280", blocked: "#b45309", cancelled: "#6b7280",
};

export default function WorkflowPanel({ projectId }: { projectId: string }) {
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const refresh = useCallback(async (runId: string) => {
    try {
      const d = await api.getRun(runId);
      setDetail(d);
      if (["succeeded", "failed", "cancelled", "paused"].includes(d.run.status) && timer.current) {
        clearInterval(timer.current); timer.current = null;
      }
    } catch (e) { setError((e as Error).message); }
  }, []);

  function startPolling(runId: string) {
    if (timer.current) clearInterval(timer.current);
    timer.current = setInterval(() => refresh(runId), 5000);
  }
  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);

  async function createAndRun() {
    setBusy(true); setError("");
    try {
      const { run } = await api.createRun(projectId);
      await api.executeRun(run.id);
      await refresh(run.id);
      startPolling(run.id);
    } catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  }

  async function cancel() {
    if (!detail) return;
    await api.cancelRun(detail.run.id);
    await refresh(detail.run.id);
  }

  return (
    <div className="card">
      <div className="row">
        <h2>Workflow</h2>
        <div className="row" style={{ gap: 8 }}>
          <button onClick={createAndRun} disabled={busy}>
            {busy ? "Starting..." : "Start 7-agent build run"}
          </button>
          {detail && !["succeeded", "failed", "cancelled"].includes(detail.run.status) && (
            <button onClick={cancel} className="secondary">Cancel</button>
          )}
        </div>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {!detail && (
        <p className="muted" style={{ marginTop: 8 }}>
          Starts the real pipeline: architect, UI designer, DB engineer, backend, frontend,
          test &amp; repair, devops. Each agent calls the AI provider; progress and failures
          are recorded honestly.
        </p>
      )}
      {detail && (
        <>
          <p style={{ marginTop: 8 }}>
            Run status:{" "}
            <strong style={{ color: STATUS_COLOR[detail.run.status] }}>{detail.run.status}</strong>
            {detail.run.error_summary && <span className="error"> - {detail.run.error_summary}</span>}
          </p>
          <table style={{ width: "100%", marginTop: 8, borderCollapse: "collapse" }}>
            <tbody>
              {detail.tasks.map((t) => (
                <tr key={t.id} style={{ borderTop: "1px solid #e5e7eb" }}>
                  <td style={{ padding: "6px 8px" }}>{t.agent_role}</td>
                  <td style={{ padding: "6px 8px" }}>{t.kind}</td>
                  <td style={{ padding: "6px 8px", color: STATUS_COLOR[t.status] }}>{t.status}</td>
                  <td style={{ padding: "6px 8px" }} className="muted">attempts: {t.attempts}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <h3 style={{ marginTop: 12 }}>Events</h3>
          <ul style={{ maxHeight: 200, overflow: "auto", fontSize: 13 }}>
            {detail.events.map((e) => (
              <li key={e.id}>
                <span className="muted">{new Date(e.created_at).toLocaleTimeString()}</span>{" "}
                <strong>{e.event_type}</strong> {e.message}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
