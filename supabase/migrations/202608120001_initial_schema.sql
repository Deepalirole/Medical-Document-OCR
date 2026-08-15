begin;

create extension if not exists pgcrypto;

create type public.organization_role as enum ('admin', 'reviewer');
create type public.review_status as enum ('HIGH', 'MEDIUM', 'LOW', 'REVIEW_REQUIRED');

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null check (length(trim(name)) > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table public.organization_members (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  role public.organization_role not null,
  created_at timestamptz not null default now(),
  unique (organization_id, user_id)
);

create table public.prescription_schemas (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  schema_key text not null check (schema_key ~ '^[a-z][a-z0-9_]*$'),
  name text not null check (length(trim(name)) > 0),
  version integer not null check (version > 0),
  definition jsonb not null check (jsonb_typeof(definition) = 'object'),
  status text not null default 'draft' check (status in ('draft', 'active', 'archived')),
  is_active boolean not null default false,
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, schema_key, version)
);

create unique index prescription_schemas_one_active_per_key
  on public.prescription_schemas (organization_id, schema_key)
  where is_active;

create table public.prescriptions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete restrict,
  uploaded_by uuid not null references auth.users(id),
  schema_id uuid not null references public.prescription_schemas(id) on delete restrict,
  original_filename text not null,
  source_mime_type text not null,
  source_storage_path text not null unique,
  source_type text not null check (source_type in ('pdf', 'image')),
  source_sha256 text not null check (length(source_sha256) = 64),
  status text not null,
  page_count integer not null default 0 check (page_count >= 0),
  approved_at timestamptz,
  approved_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check ((approved_at is null and approved_by is null) or (approved_at is not null and approved_by is not null))
);

create unique index prescriptions_org_source_dedupe
  on public.prescriptions (organization_id, source_sha256);

create table public.prescription_pages (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete restrict,
  prescription_id uuid not null references public.prescriptions(id) on delete cascade,
  page_number integer not null check (page_number > 0),
  original_image_path text not null,
  processed_image_path text,
  width integer not null check (width > 0),
  height integer not null check (height > 0),
  quality_metadata jsonb not null default '{}'::jsonb,
  preprocessing_applied jsonb not null default '[]'::jsonb check (jsonb_typeof(preprocessing_applied) = 'array'),
  status text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (prescription_id, page_number)
);

create table public.ocr_results (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete restrict,
  prescription_id uuid not null references public.prescriptions(id) on delete cascade,
  page_id uuid not null references public.prescription_pages(id) on delete cascade,
  provider text not null,
  provider_version text,
  raw_text text not null,
  confidence numeric check (confidence between 0 and 1),
  processing_ms integer not null check (processing_ms >= 0),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table public.ocr_tokens (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete restrict,
  prescription_id uuid not null references public.prescriptions(id) on delete cascade,
  page_id uuid not null references public.prescription_pages(id) on delete cascade,
  ocr_result_id uuid not null references public.ocr_results(id) on delete cascade,
  text text not null,
  confidence numeric check (confidence between 0 and 1),
  bbox jsonb,
  sequence_index integer not null check (sequence_index >= 0),
  source text not null check (source in ('ocr', 'htr', 'pdf_text')),
  created_at timestamptz not null default now(),
  unique (ocr_result_id, sequence_index)
);

create table public.extraction_runs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete restrict,
  prescription_id uuid not null references public.prescriptions(id) on delete cascade,
  schema_id uuid not null references public.prescription_schemas(id) on delete restrict,
  provider text not null,
  model text not null,
  input_hash text not null,
  raw_response jsonb,
  structured_output jsonb,
  status text not null,
  processing_ms integer not null check (processing_ms >= 0),
  error_code text,
  created_at timestamptz not null default now()
);

create table public.prescription_fields (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete restrict,
  prescription_id uuid not null references public.prescriptions(id) on delete cascade,
  schema_id uuid not null references public.prescription_schemas(id) on delete restrict,
  field_path text not null,
  field_type text not null,
  array_item_id text,
  original_value jsonb,
  current_value jsonb,
  review_status public.review_status not null,
  confidence numeric check (confidence between 0 and 1),
  evidence jsonb,
  validation jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique nulls not distinct (prescription_id, field_path, array_item_id)
);

create table public.corrections (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete restrict,
  prescription_id uuid not null references public.prescriptions(id) on delete cascade,
  prescription_field_id uuid not null references public.prescription_fields(id) on delete restrict,
  old_value jsonb,
  new_value jsonb,
  corrected_by uuid not null references auth.users(id),
  reason text,
  created_at timestamptz not null default now()
);

create table public.prescription_versions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete restrict,
  prescription_id uuid not null references public.prescriptions(id) on delete cascade,
  schema_id uuid not null references public.prescription_schemas(id) on delete restrict,
  schema_version integer not null check (schema_version > 0),
  version integer not null check (version > 0),
  structured_json jsonb not null check (jsonb_typeof(structured_json) = 'object'),
  status text not null check (status = 'APPROVED'),
  created_by uuid not null references auth.users(id),
  created_at timestamptz not null default now(),
  unique (prescription_id, version)
);

create table public.processing_jobs (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete restrict,
  prescription_id uuid not null references public.prescriptions(id) on delete cascade,
  idempotency_key text,
  stage text not null,
  status text not null,
  attempt integer not null default 1 check (attempt > 0),
  started_at timestamptz not null default now(),
  completed_at timestamptz,
  processing_ms integer check (processing_ms >= 0),
  error_code text,
  safe_error_message text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique nulls not distinct (prescription_id, idempotency_key, attempt)
);

create index organization_members_user_idx on public.organization_members(user_id);
create index organization_members_org_idx on public.organization_members(organization_id);
create index prescriptions_org_idx on public.prescriptions(organization_id);
create index prescriptions_status_idx on public.prescriptions(status);
create index prescriptions_created_idx on public.prescriptions(created_at desc);
create index prescription_pages_prescription_idx on public.prescription_pages(prescription_id);
create index ocr_results_prescription_idx on public.ocr_results(prescription_id);
create index ocr_tokens_prescription_idx on public.ocr_tokens(prescription_id);
create index ocr_tokens_page_idx on public.ocr_tokens(page_id);
create index extraction_runs_prescription_idx on public.extraction_runs(prescription_id);
create index prescription_fields_prescription_idx on public.prescription_fields(prescription_id);
create index prescription_fields_path_idx on public.prescription_fields(field_path);
create index corrections_prescription_idx on public.corrections(prescription_id);
create index prescription_versions_prescription_idx on public.prescription_versions(prescription_id);
create index processing_jobs_prescription_idx on public.processing_jobs(prescription_id);
create index processing_jobs_status_idx on public.processing_jobs(status);
create index prescription_schemas_org_active_idx on public.prescription_schemas(organization_id, is_active);

create function public.set_updated_at()
returns trigger language plpgsql set search_path = public as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create function public.is_org_member(target_organization_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.organization_members
    where organization_id = target_organization_id and user_id = auth.uid()
  );
$$;

create function public.has_org_role(target_organization_id uuid, allowed_roles public.organization_role[])
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.organization_members
    where organization_id = target_organization_id
      and user_id = auth.uid()
      and role = any(allowed_roles)
  );
$$;

revoke all on function public.is_org_member(uuid) from public;
revoke all on function public.has_org_role(uuid, public.organization_role[]) from public;
grant execute on function public.is_org_member(uuid) to authenticated, service_role;
grant execute on function public.has_org_role(uuid, public.organization_role[]) to authenticated, service_role;

create function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  insert into public.profiles (id, display_name)
  values (new.id, coalesce(new.raw_user_meta_data ->> 'display_name', split_part(new.email, '@', 1)));
  return new;
end;
$$;

create trigger on_auth_user_created
after insert on auth.users
for each row execute procedure public.handle_new_user();

create trigger organizations_updated_at before update on public.organizations
for each row execute function public.set_updated_at();
create trigger profiles_updated_at before update on public.profiles
for each row execute function public.set_updated_at();
create trigger schemas_updated_at before update on public.prescription_schemas
for each row execute function public.set_updated_at();
create trigger prescriptions_updated_at before update on public.prescriptions
for each row execute function public.set_updated_at();
create trigger pages_updated_at before update on public.prescription_pages
for each row execute function public.set_updated_at();
create trigger fields_updated_at before update on public.prescription_fields
for each row execute function public.set_updated_at();
create trigger jobs_updated_at before update on public.processing_jobs
for each row execute function public.set_updated_at();

alter table public.organizations enable row level security;
alter table public.profiles enable row level security;
alter table public.organization_members enable row level security;
alter table public.prescription_schemas enable row level security;
alter table public.prescriptions enable row level security;
alter table public.prescription_pages enable row level security;
alter table public.ocr_results enable row level security;
alter table public.ocr_tokens enable row level security;
alter table public.extraction_runs enable row level security;
alter table public.prescription_fields enable row level security;
alter table public.corrections enable row level security;
alter table public.prescription_versions enable row level security;
alter table public.processing_jobs enable row level security;

create policy organizations_select on public.organizations for select
  to authenticated using (public.is_org_member(id));
create policy organizations_admin_update on public.organizations for update
  to authenticated using (public.has_org_role(id, array['admin']::public.organization_role[]))
  with check (public.has_org_role(id, array['admin']::public.organization_role[]));

create policy profiles_select_self on public.profiles for select to authenticated using (id = auth.uid());
create policy profiles_update_self on public.profiles for update to authenticated using (id = auth.uid()) with check (id = auth.uid());

create policy members_select on public.organization_members for select
  to authenticated using (user_id = auth.uid() or public.has_org_role(organization_id, array['admin']::public.organization_role[]));
create policy members_admin_insert on public.organization_members for insert
  to authenticated with check (public.has_org_role(organization_id, array['admin']::public.organization_role[]));
create policy members_admin_update on public.organization_members for update
  to authenticated using (public.has_org_role(organization_id, array['admin']::public.organization_role[]))
  with check (public.has_org_role(organization_id, array['admin']::public.organization_role[]));
create policy members_admin_delete on public.organization_members for delete
  to authenticated using (public.has_org_role(organization_id, array['admin']::public.organization_role[]));

create policy schemas_select on public.prescription_schemas for select
  to authenticated using (public.is_org_member(organization_id));
create policy schemas_admin_insert on public.prescription_schemas for insert
  to authenticated with check (
    created_by = auth.uid() and public.has_org_role(organization_id, array['admin']::public.organization_role[])
  );
create policy schemas_admin_update on public.prescription_schemas for update
  to authenticated using (public.has_org_role(organization_id, array['admin']::public.organization_role[]))
  with check (public.has_org_role(organization_id, array['admin']::public.organization_role[]));
create policy schemas_admin_delete on public.prescription_schemas for delete
  to authenticated using (public.has_org_role(organization_id, array['admin']::public.organization_role[]));

create policy prescriptions_select on public.prescriptions for select
  to authenticated using (public.is_org_member(organization_id));
create policy prescriptions_insert on public.prescriptions for insert
  to authenticated with check (uploaded_by = auth.uid() and public.is_org_member(organization_id));
create policy prescriptions_update on public.prescriptions for update
  to authenticated using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

create policy pages_select on public.prescription_pages for select to authenticated using (public.is_org_member(organization_id));
create policy pages_insert on public.prescription_pages for insert to authenticated with check (public.is_org_member(organization_id));
create policy pages_update on public.prescription_pages for update to authenticated using (public.is_org_member(organization_id)) with check (public.is_org_member(organization_id));

create policy ocr_results_select on public.ocr_results for select to authenticated using (public.is_org_member(organization_id));
create policy ocr_tokens_select on public.ocr_tokens for select to authenticated using (public.is_org_member(organization_id));
create policy extraction_runs_select on public.extraction_runs for select to authenticated using (public.is_org_member(organization_id));
create policy fields_select on public.prescription_fields for select to authenticated using (public.is_org_member(organization_id));
create policy fields_update on public.prescription_fields for update to authenticated using (public.is_org_member(organization_id)) with check (public.is_org_member(organization_id));
create policy corrections_select on public.corrections for select to authenticated using (public.is_org_member(organization_id));
create policy corrections_insert on public.corrections for insert to authenticated with check (corrected_by = auth.uid() and public.is_org_member(organization_id));
create policy versions_select on public.prescription_versions for select to authenticated using (public.is_org_member(organization_id));
create policy jobs_select on public.processing_jobs for select to authenticated using (public.is_org_member(organization_id));

-- Machine-generated writes flow through the trusted FastAPI service role. These tables deliberately
-- expose read-only access to authenticated users; reviewer mutations use narrow API operations.

insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values
  ('prescription-source', 'prescription-source', false, 15728640, array['application/pdf','image/jpeg','image/png']),
  ('prescription-derived', 'prescription-derived', false, 15728640, array['image/png','image/jpeg'])
on conflict (id) do update set public = false;

create policy source_member_read on storage.objects for select to authenticated
using (
  bucket_id = 'prescription-source'
  and public.is_org_member(((storage.foldername(name))[1])::uuid)
);
create policy derived_member_read on storage.objects for select to authenticated
using (
  bucket_id = 'prescription-derived'
  and public.is_org_member(((storage.foldername(name))[1])::uuid)
);

commit;

