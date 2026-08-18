-- P4: multi-stage approvals.
-- An organization without a row in approval_workflows keeps the pre-existing single reviewer
-- sign-off, so this migration cannot change the behaviour of a live deployment on its own.

create table if not exists public.approval_workflows (
  organization_id uuid primary key references public.organizations(id) on delete cascade,
  stages jsonb not null,
  require_distinct_reviewers boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.prescription_approval_steps (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete restrict,
  prescription_id uuid not null references public.prescriptions(id) on delete cascade,
  stage_key text not null,
  stage_order integer not null check (stage_order >= 1),
  approved_by uuid not null references auth.users(id),
  notes text,
  created_at timestamptz not null default now(),
  unique (prescription_id, stage_key)
);

create index if not exists prescription_approval_steps_prescription_idx
  on public.prescription_approval_steps(prescription_id);
create index if not exists prescription_approval_steps_organization_idx
  on public.prescription_approval_steps(organization_id);
create index if not exists approval_workflows_organization_idx
  on public.approval_workflows(organization_id);

alter table public.approval_workflows enable row level security;
alter table public.prescription_approval_steps enable row level security;

create policy approval_workflows_member_read on public.approval_workflows
  for select to authenticated
  using (
    exists (
      select 1 from public.memberships m
      where m.organization_id = approval_workflows.organization_id
        and m.user_id = (select auth.uid())
    )
  );

create policy approval_workflows_admin_write on public.approval_workflows
  for all to authenticated
  using (
    exists (
      select 1 from public.memberships m
      where m.organization_id = approval_workflows.organization_id
        and m.user_id = (select auth.uid())
        and m.role = 'admin'
    )
  )
  with check (
    exists (
      select 1 from public.memberships m
      where m.organization_id = approval_workflows.organization_id
        and m.user_id = (select auth.uid())
        and m.role = 'admin'
    )
  );

create policy approval_steps_member_read on public.prescription_approval_steps
  for select to authenticated
  using (
    exists (
      select 1 from public.memberships m
      where m.organization_id = prescription_approval_steps.organization_id
        and m.user_id = (select auth.uid())
    )
  );

-- Sign-offs are append-only and always attributed to the acting user: no update, no delete.
create policy approval_steps_member_insert on public.prescription_approval_steps
  for insert to authenticated
  with check (
    approved_by = (select auth.uid())
    and exists (
      select 1 from public.memberships m
      where m.organization_id = prescription_approval_steps.organization_id
        and m.user_id = (select auth.uid())
    )
  );

comment on table public.prescription_approval_steps is
  'Append-only per-stage approval sign-offs gating the immutable approved version.';
