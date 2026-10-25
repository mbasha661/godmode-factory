"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { getSupabase } from "@/lib/supabase";
import { api, Project } from "@/lib/api";

export default function DashboardPage() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");

  useEffect(() => {
    getSupabase().auth.getSession().then(async ({ data }) => {
      if (!data.session) { router.replace("/login"); return; }
      setEmail(data.session.user.email || "");
      try {
        const [p, s] = await Promise.all([api.listProjects(), api.systemStatus()]);
        setProjects(p); setStatus(s);
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
          <button className="btn secondary" onClick={signOut}>Sign out</button>
        </span>
      </nav>
      <main className="container">
        {error && <p className="error" role="alert">{error}</p>}
        <div className="grid cols-4">
          <div className="card"><div className="stat">{projects ? projects.length : "-"}</div><div className="muted">Projects</div></div>
          <div className="card"><div className="stat">0</div><div className="muted">Active workflows</div></div>
          <div className="card"><div className="stat">0</div><div className="muted">Completed</div></div>
          <div className="card"><div className="stat">0</div><div className="muted">Failed</div></div>
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
            <div className="list-item" key={p.id}>
              <div className="row">
                <Link href={`/projects/${p.id}`}><strong>{p.name}</strong></Link>
                <span className="badge">{p.project_type}</span>
              </div>
              <p className="muted" style={{ marginTop: 4 }}>{p.description || "No description"}</p>
            </div>
          ))}
        </div>
      </main>
    </>
  );
}
