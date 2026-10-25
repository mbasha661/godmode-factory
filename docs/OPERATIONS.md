# Operations

## Health
- GET /health -> {"status":"ok"}
- GET /api/system/status -> environment, supabase/ai config state, active limits. Unconfigured
  backends are reported as unconfigured, never as healthy.

## Troubleshooting
- 401 on all API calls: token expired or SUPABASE_ANON_KEY mismatch.
- 503 auth_unavailable: API missing SUPABASE_* env vars.
- Provider errors: check agent_runs.error_category; quota_exhausted stops the run by design.
- Render free tier sleeps after 15 min idle: first request after idle takes ~30s (cold start).

## Backup
- Source of truth is the git repo. Per-phase ZIP backups are uploaded to the owner's Google Drive.
