# Security model and honest limits

## Enforced
- Supabase Auth (email+password). JWT verified server-side against GoTrue on every API call.
- Postgres RLS on all 14 tables + explicit owner_id filters in server queries (defense in depth).
- Cross-user access returns 404, never 403-with-existence-leak.
- Service role key and AI keys: server-side env only, never shipped to the browser, never logged.
- Artifact storage: private bucket, short-lived signed URLs only.
- Soft deletes only for user data; destructive operations need approval_requests.
- Input validation via pydantic on every endpoint; path validation on generated files (Phase 4).

## Honest limits (not hidden)
- CODE EXECUTION ISOLATION: generated code runs in a subprocess with rlimits
  (CPU, memory, wall time, output size), a scrubbed environment, and a disposable working
  directory. On the free tier there is no VM/container sandbox (no Docker on Render free,
  no Firecracker). This blocks casual mistakes and runaway resource use; it does NOT stop a
  determined adversarial program. Treat generated code as untrusted; the platform never runs it
  with production credentials in the environment.
- Free-tier quotas (Supabase 500MB db, Gemini RPD, Render spin-down) are enforced by the
  providers, not by us; the dashboard surfaces configuration state but cannot guarantee quotas.

## Prompt injection stance
User prompts and generated content are data. Agent instructions live in role definitions the
user's prompt cannot modify; agent outputs are validated against JSON schemas before use.
