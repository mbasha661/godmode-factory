"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

const TYPES = [
  { value: "web", label: "Web application" },
  { value: "mobile", label: "Mobile application (Expo)" },
  { value: "api", label: "Backend API" },
  { value: "fullstack", label: "Full-stack application" },
];

export default function NewProjectPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [projectType, setProjectType] = useState("fullstack");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      const p = await api.createProject({ name, description, project_type: projectType });
      router.replace(`/projects/${p.id}`);
    } catch (err) { setError((err as Error).message); setBusy(false); }
  }

  return (
    <main className="container" style={{ maxWidth: 640 }}>
      <div className="card">
        <h1>New project</h1>
        <p className="muted" style={{ margin: "8px 0 16px" }}>Describe the app in plain language. The Architect agent turns it into a specification you review before generation starts.</p>
        <form onSubmit={submit}>
          <label htmlFor="name">Project name</label>
          <input id="name" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} placeholder="Fleet manager" />
          <label htmlFor="description">What should it do?</label>
          <textarea id="description" rows={6} maxLength={12000} value={description} onChange={(e) => setDescription(e.target.value)}
            placeholder="Build a fleet management application with vehicle records, driver management, daily earnings, maintenance reminders, PDF reports, authentication, and a responsive dashboard." />
          <label htmlFor="type">Application type</label>
          <select id="type" value={projectType} onChange={(e) => setProjectType(e.target.value)}>
            {TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
          {error && <p className="error" role="alert">{error}</p>}
          <button className="btn" disabled={busy} type="submit">{busy ? "Creating..." : "Create project"}</button>
        </form>
      </div>
    </main>
  );
}
