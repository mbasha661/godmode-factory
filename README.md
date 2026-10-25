# GOD MODE AI SOFTWARE FACTORY

Cloud-based autonomous software development platform. Turns a natural-language app
idea into a planned, implemented, tested, and packaged software project.

## Architecture

- `apps/web` - Next.js 14 + TypeScript dashboard (Vercel, free Hobby tier)
- `apps/api` - FastAPI control plane + orchestrator + worker (Render free web service)
- `supabase/migrations` - Postgres schema, RLS policies, versioned migrations (Supabase free tier)
- AI: provider-swappable adapter (Gemini API free tier default, Groq alternate). Keys server-side only.
- Queue: Postgres-backed durable task queue (SELECT ... FOR UPDATE SKIP LOCKED). No Redis.
- Code execution: isolated subprocess worker (rlimits CPU/mem/time/disk, no prod env vars,
  disposable workspace). This is process isolation, NOT a hardened sandbox - see docs/SECURITY.md.
- Artifacts: Supabase Storage private bucket, short-lived signed URLs.

## Seven agent roles
architect, ui_designer, frontend_dev, backend_dev, db_engineer, devops, test_repair -
distinct role configs over a shared provider adapter, plus a central orchestrator.

## Docs
- docs/ARCHITECTURE.md - system design
- docs/SETUP.md - local + production setup
- docs/SECURITY.md - security model and honest limits
- docs/OPERATIONS.md - runbook
