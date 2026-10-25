# Setup

## Prereqs
- Supabase project (free): run supabase/migrations/0001..0003 in the SQL editor, in order.
- Env: copy .env.example to apps/api/.env and fill values. Web needs the NEXT_PUBLIC_ vars.

## Local dev
- API: cd apps/api && python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
  && uvicorn app.main:app --reload
- Web: cd apps/web && npm install && npm run dev

## Tests
- API: cd apps/api && .venv/bin/python -m pytest tests/ -q
- Web: cd apps/web && npm run build  (typecheck + production build)

## Deploy
- Web -> Vercel: vercel --token $VERCEL_TOKEN (project godmode-factory-web), env vars in Vercel UI.
- API -> Render: Python web service, build `pip install -r requirements.txt`,
  start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`, root dir apps/api.
