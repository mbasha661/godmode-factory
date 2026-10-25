"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Project } from "@/lib/api";
import WorkflowPanel from "./WorkflowPanel";

export default function ProjectPage({ params }: { params: { id: string } }) {
  const router = useRouter();
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.getProject(params.id).then(setProject).catch((e) => setError((e as Error).message));
  }, [params.id]);

  async function remove() {
    if (!confirm("Archive this project? This is a soft delete.")) return;
    await api.deleteProject(params.id);
    router.replace("/dashboard");
  }

  if (error) return <main className="container"><p className="error" role="alert">{error}</p></main>;
  if (!project) return <main className="container"><p className="muted">Loading...</p></main>;

  return (
    <main className="container">
      <div className="card">
        <div className="row">
          <h1>{project.name}</h1>
          <span className="badge">{project.project_type}</span>
        </div>
        <p style={{ margin: "12px 0" }}>{project.description}</p>
        <p className="muted">Status: {project.status} - Created {new Date(project.created_at).toLocaleString()}</p>
      </div>
      <WorkflowPanel projectId={params.id} />
      <button className="btn danger" onClick={remove}>Delete project</button>
    </main>
  );
}
