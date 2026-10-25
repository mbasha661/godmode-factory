-- 0001_init.sql - God Mode AI Software Factory core schema
-- 14 tables, UUID ids, timestamps, constraints, indexes, foreign keys, audit fields.

create extension if not exists "pgcrypto";

-- ---------- profiles (mirrors auth.users) ----------
create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  display_name text,
  is_admin boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------- projects ----------
create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 120),
  description text not null default '' check (char_length(description) <= 12000),
  project_type text not null default 'fullstack'
    check (project_type in ('web','mobile','api','fullstack')),
  status text not null default 'draft'
    check (status in ('draft','active','archived','deleted')),
  created_by uuid not null references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists projects_owner_idx on public.projects(owner_id);

create table if not exists public.project_members (
  project_id uuid not null references public.projects(id) on delete cascade,
  user_id uuid not null references public.profiles(id) on delete cascade,
  role text not null default 'viewer' check (role in ('owner','editor','viewer')),
  created_at timestamptz not null default now(),
  primary key (project_id, user_id)
);

-- ---------- specifications ----------
create table if not exists public.project_specifications (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  version int not null default 1,
  status text not null default 'draft'
    check (status in ('draft','pending_approval','approved','rejected','superseded')),
  spec jsonb not null default '{}'::jsonb,
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now(),
  unique (project_id, version)
);
create index if not exists project_specifications_project_idx on public.project_specifications(project_id);

-- ---------- agent definitions (the seven roles) ----------
create table if not exists public.agent_definitions (
  id uuid primary key default gen_random_uuid(),
  role text not null unique check (role in
    ('architect','ui_designer','frontend_dev','backend_dev','db_engineer','devops','test_repair')),
  display_name text not null,
  instructions text not null default '',
  output_schema jsonb not null default '{}'::jsonb,
  config jsonb not null default '{}'::jsonb,
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- ---------- workflow runs ----------
create table if not exists public.workflow_runs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null references public.projects(id) on delete cascade,
  specification_id uuid references public.project_specifications(id),
  status text not null default 'pending'
    check (status in ('pending','running','paused','succeeded','failed','cancelled','awaiting_approval')),
  current_task_id uuid,
  error_summary text,
  started_at timestamptz,
  finished_at timestamptz,
  max_duration_minutes int not null default 30,
  created_by uuid not null references public.profiles(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists workflow_runs_project_idx on public.workflow_runs(project_id);
create index if not exists workflow_runs_status_idx on public.workflow_runs(status);

-- ---------- tasks ----------
create table if not exists public.tasks (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.workflow_runs(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  agent_role text not null references public.agent_definitions(role),
  title text not null check (char_length(title) between 1 and 200),
  kind text not null default 'generate'
    check (kind in ('spec','design','generate','migrate','test','repair','build','package','deploy_prep')),
  status text not null default 'pending'
    check (status in ('pending','ready','running','succeeded','failed','blocked','cancelled')),
  sequence int not null,
  input jsonb not null default '{}'::jsonb,
  output jsonb,
  error_summary text,
  attempts int not null default 0,
  max_attempts int not null default 2,
  started_at timestamptz,
  finished_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (run_id, sequence)
);
create index if not exists tasks_run_idx on public.tasks(run_id);
create index if not exists tasks_status_idx on public.tasks(status);

create table if not exists public.task_dependencies (
  task_id uuid not null references public.tasks(id) on delete cascade,
  depends_on_task_id uuid not null references public.tasks(id) on delete cascade,
  primary key (task_id, depends_on_task_id),
  check (task_id <> depends_on_task_id)
);
create index if not exists task_dependencies_dep_idx on public.task_dependencies(depends_on_task_id);

-- ---------- agent runs (each AI invocation) ----------
create table if not exists public.agent_runs (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references public.tasks(id) on delete cascade,
  run_id uuid not null references public.workflow_runs(id) on delete cascade,
  agent_role text not null references public.agent_definitions(role),
  provider text,
  model text,
  attempt int not null default 1,
  status text not null default 'running'
    check (status in ('running','succeeded','failed','cancelled')),
  input_redacted jsonb not null default '{}'::jsonb,
  output jsonb,
  error_category text check (error_category in
    ('provider_unavailable','quota_exhausted','invalid_model_output','auth_failure',
     'database_failure','code_execution_failure','test_failure','build_failure',
     'artifact_storage_failure','deployment_failure', null)),
  error_summary text,
  prompt_tokens int,
  completion_tokens int,
  duration_ms int,
  created_at timestamptz not null default now()
);
create index if not exists agent_runs_task_idx on public.agent_runs(task_id);
create index if not exists agent_runs_run_idx on public.agent_runs(run_id);

-- ---------- execution events (structured log) ----------
create table if not exists public.execution_events (
  id bigint generated always as identity primary key,
  run_id uuid references public.workflow_runs(id) on delete cascade,
  task_id uuid references public.tasks(id) on delete cascade,
  project_id uuid references public.projects(id) on delete cascade,
  agent_role text,
  level text not null default 'info' check (level in ('debug','info','warning','error')),
  event_type text not null,
  message text not null default '',
  data jsonb not null default '{}'::jsonb,
  correlation_id uuid not null default gen_random_uuid(),
  created_at timestamptz not null default now()
);
create index if not exists execution_events_run_idx on public.execution_events(run_id);
create index if not exists execution_events_project_idx on public.execution_events(project_id);

-- ---------- artifacts ----------
create table if not exists public.artifacts (
  id uuid primary key default gen_random_uuid(),
  run_id uuid not null references public.workflow_runs(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  kind text not null check (kind in
    ('source_zip','test_report','architecture_doc','build_log','env_template','deploy_instructions','other')),
  storage_path text not null,
  filename text not null,
  size_bytes bigint not null default 0 check (size_bytes >= 0),
  sha256 text not null default '',
  content_type text not null default 'application/octet-stream',
  created_by uuid references public.profiles(id),
  created_at timestamptz not null default now()
);
create index if not exists artifacts_run_idx on public.artifacts(run_id);
create index if not exists artifacts_project_idx on public.artifacts(project_id);

-- ---------- approval requests ----------
create table if not exists public.approval_requests (
  id uuid primary key default gen_random_uuid(),
  run_id uuid references public.workflow_runs(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  kind text not null check (kind in
    ('spec_review','public_deploy','paid_service','data_deletion','destructive_migration','publish_source','secret_access','other')),
  status text not null default 'pending' check (status in ('pending','approved','rejected','expired')),
  summary text not null,
  details jsonb not null default '{}'::jsonb,
  decided_by uuid references public.profiles(id),
  decided_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists approval_requests_project_idx on public.approval_requests(project_id);

-- ---------- provider configurations (no secrets stored here) ----------
create table if not exists public.provider_configurations (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references public.profiles(id) on delete cascade,
  provider text not null check (provider in ('gemini','groq')),
  model text not null,
  secret_ref text not null default '',   -- reference to server-side secret name, never the secret itself
  is_default boolean not null default false,
  enabled boolean not null default true,
  limits jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (owner_id, provider, model)
);

-- ---------- usage ledger ----------
create table if not exists public.usage_ledger (
  id bigint generated always as identity primary key,
  owner_id uuid not null references public.profiles(id) on delete cascade,
  run_id uuid references public.workflow_runs(id) on delete set null,
  provider text not null,
  model text not null,
  prompt_tokens int not null default 0,
  completion_tokens int not null default 0,
  requests int not null default 1,
  created_at timestamptz not null default now()
);
create index if not exists usage_ledger_owner_idx on public.usage_ledger(owner_id, created_at);

-- ---------- updated_at trigger ----------
create or replace function public.touch_updated_at() returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

do $$
declare t text;
begin
  foreach t in array array['profiles','projects','agent_definitions','workflow_runs','tasks','provider_configurations']
  loop
    execute format('drop trigger if exists touch_updated_at on public.%I;
                    create trigger touch_updated_at before update on public.%I
                    for each row execute function public.touch_updated_at();', t, t);
  end loop;
end $$;
