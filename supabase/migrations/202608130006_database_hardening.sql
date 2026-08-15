begin;

-- PostgreSQL grants EXECUTE to PUBLIC for new functions by default. Remove that
-- implicit access and then restore only the application RPC surface.
revoke all on function public.set_updated_at() from public, anon, authenticated;
revoke all on function public.handle_new_user() from public, anon, authenticated;
revoke all on function public.approve_prescription(uuid) from public, anon, authenticated;
revoke all on function public.flatten_jsonb(jsonb, text) from public, anon, authenticated;
revoke all on function public.rls_auto_enable() from public, anon, authenticated;
revoke all on function public.is_org_member(uuid) from public, anon, authenticated;
revoke all on function public.has_org_role(uuid, public.organization_role[])
  from public, anon, authenticated;
revoke all on function public.correct_prescription_field(uuid, jsonb, text)
  from public, anon, authenticated;
revoke all on function public.activate_prescription_schema(uuid)
  from public, anon, authenticated;
revoke all on function public.approve_prescription_snapshot(uuid, jsonb)
  from public, anon, authenticated;
revoke all on function public.add_prescription_array_item(uuid, text, jsonb)
  from public, anon, authenticated;
revoke all on function public.remove_prescription_array_item(uuid, text)
  from public, anon, authenticated;
revoke all on function public.organization_processing_metrics(uuid)
  from public, anon, authenticated;

grant execute on function public.is_org_member(uuid) to authenticated, service_role;
grant execute on function public.has_org_role(uuid, public.organization_role[])
  to authenticated, service_role;
grant execute on function public.correct_prescription_field(uuid, jsonb, text)
  to authenticated, service_role;
grant execute on function public.activate_prescription_schema(uuid)
  to authenticated, service_role;
grant execute on function public.approve_prescription_snapshot(uuid, jsonb)
  to authenticated, service_role;
grant execute on function public.add_prescription_array_item(uuid, text, jsonb)
  to authenticated, service_role;
grant execute on function public.remove_prescription_array_item(uuid, text)
  to authenticated, service_role;
grant execute on function public.organization_processing_metrics(uuid)
  to authenticated, service_role;

-- Cache auth.uid() once per statement instead of evaluating it for each row.
drop policy profiles_select_self on public.profiles;
create policy profiles_select_self on public.profiles for select
  to authenticated using (id = (select auth.uid()));

drop policy profiles_update_self on public.profiles;
create policy profiles_update_self on public.profiles for update
  to authenticated using (id = (select auth.uid()))
  with check (id = (select auth.uid()));

drop policy members_select on public.organization_members;
create policy members_select on public.organization_members for select
  to authenticated using (
    user_id = (select auth.uid())
    or public.has_org_role(organization_id, array['admin']::public.organization_role[])
  );

drop policy schemas_admin_insert on public.prescription_schemas;
create policy schemas_admin_insert on public.prescription_schemas for insert
  to authenticated with check (
    created_by = (select auth.uid())
    and public.has_org_role(organization_id, array['admin']::public.organization_role[])
  );

drop policy prescriptions_insert on public.prescriptions;
create policy prescriptions_insert on public.prescriptions for insert
  to authenticated with check (
    uploaded_by = (select auth.uid())
    and public.is_org_member(organization_id)
  );

drop policy corrections_insert on public.corrections;
create policy corrections_insert on public.corrections for insert
  to authenticated with check (
    corrected_by = (select auth.uid())
    and public.is_org_member(organization_id)
  );

-- Index every foreign-key column that is not already the leading column of an
-- existing index. This keeps deletes/updates on referenced rows predictable.
create index if not exists corrections_corrected_by_idx
  on public.corrections(corrected_by);
create index if not exists corrections_organization_idx
  on public.corrections(organization_id);
create index if not exists corrections_field_idx
  on public.corrections(prescription_field_id);
create index if not exists extraction_runs_organization_idx
  on public.extraction_runs(organization_id);
create index if not exists extraction_runs_schema_idx
  on public.extraction_runs(schema_id);
create index if not exists ocr_results_organization_idx
  on public.ocr_results(organization_id);
create index if not exists ocr_results_page_idx
  on public.ocr_results(page_id);
create index if not exists ocr_tokens_organization_idx
  on public.ocr_tokens(organization_id);
create index if not exists prescription_fields_organization_idx
  on public.prescription_fields(organization_id);
create index if not exists prescription_fields_schema_idx
  on public.prescription_fields(schema_id);
create index if not exists prescription_pages_organization_idx
  on public.prescription_pages(organization_id);
create index if not exists prescription_schemas_created_by_idx
  on public.prescription_schemas(created_by);
create index if not exists prescription_versions_created_by_idx
  on public.prescription_versions(created_by);
create index if not exists prescription_versions_organization_idx
  on public.prescription_versions(organization_id);
create index if not exists prescription_versions_schema_idx
  on public.prescription_versions(schema_id);
create index if not exists prescriptions_approved_by_idx
  on public.prescriptions(approved_by);
create index if not exists prescriptions_schema_idx
  on public.prescriptions(schema_id);
create index if not exists prescriptions_uploaded_by_idx
  on public.prescriptions(uploaded_by);
create index if not exists processing_jobs_organization_idx
  on public.processing_jobs(organization_id);

commit;
