begin;

create or replace function public.correct_prescription_field(
  target_field_id uuid,
  replacement_value jsonb,
  correction_reason text default null
)
returns public.prescription_fields
language plpgsql
security definer
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
  set current_value = replacement_value,
      review_status = 'HIGH',
      validation = jsonb_build_object('valid', true, 'warnings', '[]'::jsonb, 'reviewed_by', auth.uid())
  where id = target_field_id
  returning * into updated_field;
  return updated_field;
end;
$$;

create or replace function public.flatten_jsonb(value jsonb, prefix text default '')
returns table(path text, leaf jsonb)
language plpgsql
immutable
set search_path = public
as $$
declare
  item record;
  child_path text;
begin
  if jsonb_typeof(value) = 'object' then
    if value = '{}'::jsonb then
      return query select prefix, value;
    else
      for item in select * from jsonb_each(value) loop
        child_path := case when prefix = '' then item.key else prefix || '.' || item.key end;
        return query select * from public.flatten_jsonb(item.value, child_path);
      end loop;
    end if;
  elsif jsonb_typeof(value) = 'array' then
    if value = '[]'::jsonb then
      return query select prefix, value;
    else
      for item in select element, ordinality - 1 as index from jsonb_array_elements(value) with ordinality as a(element, ordinality) loop
        child_path := prefix || '[' || item.index || ']';
        return query select * from public.flatten_jsonb(item.element, child_path);
      end loop;
    end if;
  else
    return query select prefix, value;
  end if;
end;
$$;

revoke all on function public.flatten_jsonb(jsonb, text) from public, anon, authenticated;

create function public.activate_prescription_schema(target_schema_id uuid)
returns public.prescription_schemas
language plpgsql
security definer
set search_path = public
as $$
declare
  target public.prescription_schemas;
begin
  select * into target from public.prescription_schemas where id = target_schema_id for update;
  if target is null then raise exception 'SCHEMA_NOT_FOUND' using errcode = 'P0002'; end if;
  if not public.has_org_role(target.organization_id, array['admin']::public.organization_role[]) then
    raise exception 'ACCESS_DENIED' using errcode = '42501';
  end if;
  update public.prescription_schemas
  set is_active = false, status = case when status = 'active' then 'archived' else status end
  where organization_id = target.organization_id and schema_key = target.schema_key and id <> target.id;
  update public.prescription_schemas set is_active = true, status = 'active'
  where id = target.id returning * into target;
  return target;
end;
$$;

create function public.approve_prescription_snapshot(
  target_prescription_id uuid,
  approved_snapshot jsonb
)
returns public.prescription_versions
language plpgsql
security definer
set search_path = public
as $$
declare
  target public.prescriptions;
  schema_row public.prescription_schemas;
  next_version integer;
  approved public.prescription_versions;
begin
  select * into target from public.prescriptions where id = target_prescription_id for update;
  if target is null then raise exception 'PRESCRIPTION_NOT_FOUND' using errcode = 'P0002'; end if;
  if not public.is_org_member(target.organization_id) then raise exception 'ACCESS_DENIED' using errcode = '42501'; end if;
  if jsonb_typeof(approved_snapshot) <> 'object' then
    raise exception 'INVALID_SNAPSHOT' using errcode = '23514';
  end if;
  if exists (
    select 1 from public.prescription_fields
    where prescription_id = target.id and review_status = 'REVIEW_REQUIRED'
  ) then
    raise exception 'UNRESOLVED_REVIEW_FIELDS' using errcode = '23514';
  end if;
  if exists (
    with expected as (
      select field_path as path, current_value as leaf
      from public.prescription_fields where prescription_id = target.id
    ), actual as (
      select * from public.flatten_jsonb(approved_snapshot)
    )
    select 1 from expected full join actual using (path)
    where expected.path is null or actual.path is null or expected.leaf is distinct from actual.leaf
  ) then
    raise exception 'SNAPSHOT_FIELD_MISMATCH' using errcode = '23514';
  end if;

  select * into schema_row from public.prescription_schemas where id = target.schema_id;
  select coalesce(max(version), 0) + 1 into next_version
  from public.prescription_versions where prescription_id = target.id;

  insert into public.prescription_versions (
    organization_id, prescription_id, schema_id, schema_version, version,
    structured_json, status, created_by
  ) values (
    target.organization_id, target.id, target.schema_id, schema_row.version, next_version,
    approved_snapshot, 'APPROVED', auth.uid()
  ) returning * into approved;

  update public.prescriptions
  set status = 'APPROVED', approved_at = now(), approved_by = auth.uid()
  where id = target.id;
  return approved;
end;
$$;

revoke execute on function public.approve_prescription(uuid) from authenticated;
grant execute on function public.correct_prescription_field(uuid, jsonb, text) to authenticated;
grant execute on function public.activate_prescription_schema(uuid) to authenticated;
grant execute on function public.approve_prescription_snapshot(uuid, jsonb) to authenticated;

commit;

