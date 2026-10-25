-- 0002_rls.sql - Row-level security: users see and touch only their own data.

alter table public.profiles enable row level security;
alter table public.projects enable row level security;
alter table public.project_members enable row level security;
alter table public.project_specifications enable row level security;
alter table public.agent_definitions enable row level security;
alter table public.workflow_runs enable row level security;
alter table public.tasks enable row level security;
alter table public.task_dependencies enable row level security;
alter table public.agent_runs enable row level security;
alter table public.execution_events enable row level security;
alter table public.artifacts enable row level security;
alter table public.approval_requests enable row level security;
alter table public.provider_configurations enable row level security;
alter table public.usage_ledger enable row level security;

-- helper: is the current user a member (any role) of the project?
create or replace function public.is_project_member(p_project_id uuid)
returns boolean language sql security definer stable set search_path = public as $$
  select exists (
    select 1 from public.projects p
    where p.id = p_project_id and (p.owner_id = auth.uid())
  ) or exists (
    select 1 from public.project_members m
    where m.project_id = p_project_id and m.user_id = auth.uid()
  );
$$;

-- helper: is current user owner/editor of the project?
create or replace function public.can_edit_project(p_project_id uuid)
returns boolean language sql security definer stable set search_path = public as $$
  select exists (
    select 1 from public.projects p
    where p.id = p_project_id and p.owner_id = auth.uid()
  ) or exists (
    select 1 from public.project_members m
    where m.project_id = p_project_id and m.user_id = auth.uid() and m.role in ('owner','editor')
  );
$$;

-- profiles
create policy profiles_select_own on public.profiles for select using (id = auth.uid());
create policy profiles_update_own on public.profiles for update using (id = auth.uid()) with check (id = auth.uid());

-- projects
create policy projects_select_member on public.projects for select using (public.is_project_member(id));
create policy projects_insert_owner on public.projects for insert
  with check (owner_id = auth.uid() and created_by = auth.uid());
create policy projects_update_owner on public.projects for update using (owner_id = auth.uid());
create policy projects_delete_owner on public.projects for delete using (owner_id = auth.uid());

-- project_members: visible to project members; only owner manages
create policy members_select_member on public.project_members for select using (public.is_project_member(project_id));
create policy members_manage_owner on public.project_members for all
  using (exists (select 1 from public.projects p where p.id = project_id and p.owner_id = auth.uid()))
  with check (exists (select 1 from public.projects p where p.id = project_id and p.owner_id = auth.uid()));

-- specifications
create policy specs_select_member on public.project_specifications for select using (public.is_project_member(project_id));
create policy specs_write_editor on public.project_specifications for insert with check (public.can_edit_project(project_id));
create policy specs_update_editor on public.project_specifications for update using (public.can_edit_project(project_id));

-- agent definitions: readable by any signed-in user; writes only by service role (no client policy)
create policy agent_definitions_select on public.agent_definitions for select using (auth.role() = 'authenticated');

-- workflow runs
create policy runs_select_member on public.workflow_runs for select using (public.is_project_member(project_id));
create policy runs_insert_editor on public.workflow_runs for insert
  with check (public.can_edit_project(project_id) and created_by = auth.uid());
create policy runs_update_editor on public.workflow_runs for update using (public.can_edit_project(project_id));

-- tasks
create policy tasks_select_member on public.tasks for select using (public.is_project_member(project_id));
create policy tasks_write_editor on public.tasks for insert with check (public.can_edit_project(project_id));
create policy tasks_update_editor on public.tasks for update using (public.can_edit_project(project_id));

-- task dependencies: through parent task's project
create policy taskdeps_select_member on public.task_dependencies for select using (
  exists (select 1 from public.tasks t where t.id = task_id and public.is_project_member(t.project_id)));
create policy taskdeps_write_editor on public.task_dependencies for insert with check (
  exists (select 1 from public.tasks t where t.id = task_id and public.can_edit_project(t.project_id)));

-- agent runs
create policy agentruns_select_member on public.agent_runs for select using (
  exists (select 1 from public.workflow_runs r where r.id = run_id and public.is_project_member(r.project_id)));

-- execution events
create policy events_select_member on public.execution_events for select using (public.is_project_member(project_id));

-- artifacts
create policy artifacts_select_member on public.artifacts for select using (public.is_project_member(project_id));
create policy artifacts_insert_editor on public.artifacts for insert with check (public.can_edit_project(project_id));

-- approval requests
create policy approvals_select_member on public.approval_requests for select using (public.is_project_member(project_id));
create policy approvals_update_editor on public.approval_requests for update using (public.can_edit_project(project_id));

-- provider configurations: owner only
create policy provider_configs_owner on public.provider_configurations for all
  using (owner_id = auth.uid()) with check (owner_id = auth.uid());

-- usage ledger: owner reads own
create policy usage_ledger_owner on public.usage_ledger for select using (owner_id = auth.uid());
