# Architecture

## Overview
Browser -> Next.js web (Vercel) -> FastAPI control plane (Render) -> Supabase Postgres/Auth/Storage.
A Postgres-backed queue drives durable workflow runs; an in-process worker claims tasks with
FOR UPDATE SKIP LOCKED. AI calls go through a provider adapter (Gemini default, Groq alternate).

## Trust boundaries
- Browser only ever sees the Supabase anon key and the API URL.
- Service role key, AI keys: server env only.
- Generated code executes in a subprocess worker: rlimits, cwd=jail dir, scrubbed env, no network
  allowlist guarantees. Honest label: process isolation, not a hardened sandbox. See SECURITY.md.

## Data flow for a build run
1. POST /api/projects -> row in `projects` (owner = caller).
2. Architect agent -> `project_specifications` (pending_approval).
3. User approves -> orchestrator creates `tasks` + `task_dependencies` from the plan graph.
4. Worker claims ready tasks sequentially (MAX_CONCURRENT_AI_TASKS=1), records `agent_runs`,
   `execution_events`, `usage_ledger`.
5. test_repair runs generated tests in the execution worker; bounded repairs.
6. Packaging step zips the workspace -> private Supabase Storage -> `artifacts` row with sha256.
7. Signed URL (short-lived) powers the download button.

## Failure model
- Every run/task has persisted status; process restart resumes from DB state (Phase 3).
- Error categories per spec section 13 recorded on agent_runs.error_category.
- Quota/auth provider failures are not retried indefinitely (exponential backoff, capped).
