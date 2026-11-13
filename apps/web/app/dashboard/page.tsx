"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getSupabase } from "@/lib/supabase";
import { api, Project } from "@/lib/api";
import { ThemeToggle } from "../theme";
import ProjectStatus from "./ProjectStatus";

export default function DashboardPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [runCounts, setRunCounts] = useState<{ active: number; completed: number; failed: number } | null>(null);

  useEffect(() => {
    getSupabase().auth.getSession().then(async ({ data }) => {
      if (!data.session) { router.replace("/login"); return; }
      setEmail(data.session.user.email || "");
      try {
        const [p, s] = await Promise.all([api.listProjects(), api.systemStatus()]);
        setProjects(p); setStatus(s);
        const { data: runs } = await getSupabase().from("workflow_runs").select("status");
        const counts = { active: 0, completed: 0, failed: 0 };
        (runs || []).forEach((r) => {
          if (r.status === "running" || r.status === "executing" || r.status === "pending") counts.active++;
          else if (r.status === "succeeded" || r.status === "completed") counts.completed++;
          else if (r.status === "failed" || r.status === "cancelled") counts.failed++;
        });
        setRunCounts(counts);
      } catch (e) { setError((e as Error).message); }
    });
  }, [router]);

  async function signOut() {
    await getSupabase().auth.signOut();
    router.replace("/login");
  }

  const limits = (status?.limits || {}) as Record<string, number>;

  return (
    <>
      <nav className="topnav">
        <span className="brand">GOD MODE FACTORY</span>
        <span className="row">
          <span className="muted">{email}</span>
          <ThemeToggle />
          <button className="btn secondary" onClick={signOut}>Sign out</button>
        </span>
      </nav>
      <main className="container">
        {error && <p className="error" role="alert">{error}</p>}
        <div className="grid cols-4">
          <div className="card"><div className="stat">{projects ? projects.length : "-"}</div><div className="muted">Projects</div></div>
          <div className="card"><div className="stat">{runCounts ? runCounts.active : "-"}</div><div className="muted">Active workflows</div></div>
          <div className="card"><div className="stat">{runCounts ? runCounts.completed : "-"}</div><div className="muted">Completed</div></div>
          <div className="card"><div className="stat">{runCounts ? runCounts.failed : "-"}</div><div className="muted">Failed</div></div>
        </div>
        <div className="card">
          <div className="row">
            <h2>System</h2>
            {status && (
              <span className={`badge ${status.ai_provider_configured ? "ok" : "warn"}`}>
                AI provider: {String(status.ai_provider)}{status.ai_provider_configured ? "" : " (not configured)"}
              </span>
            )}
          </div>
          {status && (
            <p className="muted" style={{ marginTop: 8 }}>
              Limits: {limits.max_concurrent_ai_tasks} concurrent AI task, {limits.max_tasks_per_run} tasks/run,
              repairs {limits.max_repair_attempts}, prompt {limits.max_prompt_chars} chars,
              run timeout {limits.max_workflow_duration_minutes} min
            </p>
          )}
        </div>
        <div className="card">
          <div className="row">
            <h2>Projects</h2>
            <Link className="btn" href="/projects/new">New project</Link>
          </div>
          {projects === null && <p className="muted">Loading...</p>}
          {projects?.length === 0 && <p className="muted" style={{ marginTop: 8 }}>No projects yet. Create one to start a build.</p>}
          {projects?.map((p) => (
            <ProjectStatus key={p.id} project={p} />
          ))}
        </div>
      </main>
    </>
  );
}
