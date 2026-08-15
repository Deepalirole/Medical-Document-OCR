begin;

create function public.correct_prescription_field(
  target_field_id uuid,
  replacement_value jsonb,
  correction_reason text default null
)
returns public.prescription_fields
language plpgsql
security invoker
set search_path = public
as $$
declare
  current_field public.prescription_fields;
  updated_field public.prescription_fields;
begin
  select * into current_field from public.prescription_fields where id = target_field_id for update;
  if current_field is null then
    raise exception 'FIELD_NOT_FOUND' using errcode = 'P0002';
  end if;
  if not public.is_org_member(current_field.organization_id) then
    raise exception 'ACCESS_DENIED' using errcode = '42501';
  end if;

  insert into public.corrections (
    organization_id, prescription_id, prescription_field_id, old_value, new_value, corrected_by, reason
  ) values (
    current_field.organization_id, current_field.prescription_id, current_field.id,
    current_field.current_value, replacement_value, auth.uid(), correction_reason
  );

  update public.prescription_fields
  set current_value = replacement_value, review_status = 'REVIEW_REQUIRED'
  where id = target_field_id
  returning * into updated_field;
  return updated_field;
end;
$$;

grant execute on function public.correct_prescription_field(uuid, jsonb, text) to authenticated;

create function public.approve_prescription(target_prescription_id uuid)
returns public.prescription_versions
language plpgsql
security invoker
set search_path = public
as $$
declare
  target public.prescriptions;
  schema_row public.prescription_schemas;
  snapshot jsonb;
  next_version integer;
  approved public.prescription_versions;
begin
  select * into target from public.prescriptions where id = target_prescription_id for update;
  if target is null then raise exception 'PRESCRIPTION_NOT_FOUND' using errcode = 'P0002'; end if;
  if not public.is_org_member(target.organization_id) then raise exception 'ACCESS_DENIED' using errcode = '42501'; end if;
  if exists (
    select 1 from public.prescription_fields
    where prescription_id = target.id and review_status = 'REVIEW_REQUIRED'
  ) then
    raise exception 'UNRESOLVED_REVIEW_FIELDS' using errcode = '23514';
  end if;

  select * into schema_row from public.prescription_schemas where id = target.schema_id;
  select coalesce(max(version), 0) + 1 into next_version
  from public.prescription_versions where prescription_id = target.id;

  select coalesce(jsonb_object_agg(field_path, current_value order by field_path), '{}'::jsonb)
  into snapshot from public.prescription_fields where prescription_id = target.id;

  insert into public.prescription_versions (
    organization_id, prescription_id, schema_id, schema_version, version,
    structured_json, status, created_by
  ) values (
    target.organization_id, target.id, target.schema_id, schema_row.version, next_version,
    snapshot, 'APPROVED', auth.uid()
  ) returning * into approved;

  update public.prescriptions
  set status = 'APPROVED', approved_at = now(), approved_by = auth.uid()
  where id = target.id;
  return approved;
end;
$$;

grant execute on function public.approve_prescription(uuid) to authenticated;

commit;

