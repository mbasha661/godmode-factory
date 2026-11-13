"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { getSupabase } from "@/lib/supabase";
import { Project } from "@/lib/api";

type RunInfo = {
  id: string; status: string; created_at: string; finished_at: string | null; error_summary: string | null;
};
type TaskInfo = { agent_role: string; status: string };

function badgeClass(status: string): string {
  if (status === "succeeded" || status === "completed") return "badge ok";
  if (status === "failed" || status === "cancelled") return "badge err";
  if (status === "running" || status === "executing" || status === "pending") return "badge running";
  return "badge warn";
}
function chipClass(status: string): string {
  if (status === "succeeded" || status === "completed") return "task-chip ok";
  if (status === "failed") return "task-chip err";
  if (status === "running" || status === "executing") return "task-chip running";
  return "task-chip";
}

export default function ProjectStatus({ project }: { project: Project }) {
  const [run, setRun] = useState<RunInfo | null>(null);
  const [tasks, setTasks] = useState<TaskInfo[]>([]);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    let live = true;
    (async () => {
      const sb = getSupabase();
      const { data: runs } = await sb
        .from("workflow_runs")
        .select("id,status,created_at,finished_at,error_summary")
        .eq("project_id", project.id)
        .order("created_at", { ascending: false })
        .limit(1);
      if (!live) return;
      const latest = (runs && runs[0]) || null;
      setRun(latest);
      if (latest) {
        const { data: t } = await sb
          .from("tasks")
          .select("agent_role,status")
          .eq("run_id", latest.id)
          .order("created_at", { ascending: true });
        if (live) setTasks(t || []);
      }
      if (live) setLoaded(true);
    })().catch(() => setLoaded(true));
    return () => { live = false; };
  }, [project.id]);

  const done = tasks.filter((t) => t.status === "succeeded" || t.status === "completed").length;
  const pct = tasks.length ? Math.round((done / tasks.length) * 100) : 0;

  return (
    <div className="list-item">
      <div className="row">
        <Link href={`/projects/${project.id}`}><strong>{project.name}</strong></Link>
        <span className="row" style={{ gap: 6 }}>
          <span className="badge">{project.project_type}</span>
          {run && <span className={badgeClass(run.status)}>{run.status}</span>}
          {loaded && !run && <span className="badge">no runs yet</span>}
        </span>
      </div>
      <p className="muted" style={{ marginTop: 4 }}>{project.description || "No description"}</p>
      {run && (
        <div className="proj-status">
          <span className="muted">
            Last run {new Date(run.created_at).toLocaleString()}
            {run.finished_at ? ` - finished ${new Date(run.finished_at).toLocaleString()}` : " - in progress"}
          </span>
        </div>
      )}
      {run && tasks.length > 0 && (
        <>
          <div className="progress-track"><div className="progress-fill" style={{ width: `${pct}%` }} /></div>
          <div style={{ marginTop: 6 }}>
            {tasks.map((t, i) => (
              <span key={i} className={chipClass(t.status)}>{t.agent_role}</span>
            ))}
          </div>
        </>
      )}
      {run?.error_summary && <p className="error" style={{ marginTop: 6 }}>{run.error_summary}</p>}
      <div style={{ marginTop: 8 }}>
        <Link className="btn secondary" href={`/projects/${project.id}`}>Open project &amp; preview</Link>
      </div>
    </div>
  );
}
