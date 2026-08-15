begin;

create function public.add_prescription_array_item(
  target_prescription_id uuid,
  target_array_path text,
  item_values jsonb
)
returns setof public.prescription_fields
language plpgsql
security definer
set search_path = public
as $$
declare
  target public.prescriptions;
  schema_row public.prescription_schemas;
  section jsonb;
  item_definition jsonb;
  field_record record;
  created_field public.prescription_fields;
  item_id text := gen_random_uuid()::text;
  next_index integer;
begin
  select * into target from public.prescriptions where id = target_prescription_id;
  if target is null then raise exception 'PRESCRIPTION_NOT_FOUND' using errcode = 'P0002'; end if;
  if not public.is_org_member(target.organization_id) then raise exception 'ACCESS_DENIED' using errcode = '42501'; end if;
  select * into schema_row from public.prescription_schemas where id = target.schema_id;
  select entry into section
  from jsonb_array_elements(schema_row.definition -> 'sections') entry
  where entry ->> 'key' = target_array_path
    and entry ->> 'type' in ('array', 'medicine_list');
  if section is null or jsonb_typeof(item_values) <> 'object' then
    raise exception 'ARRAY_PATH_INVALID' using errcode = '23514';
  end if;
  item_definition := section -> 'item_schema';
  if not (item_definition ? 'type') and exists (
    select 1 from jsonb_object_keys(item_values) supplied_key
    where not item_definition ? supplied_key
  ) then
    raise exception 'ARRAY_FIELD_INVALID' using errcode = '23514';
  end if;

  select coalesce(max((substring(field_path from '\[([0-9]+)\]'))::integer), -1) + 1
  into next_index from public.prescription_fields
  where prescription_id = target.id and field_path like target_array_path || '[%';

  if item_definition ? 'type' then
    if not (item_values ? 'value') then
      raise exception 'SCALAR_ARRAY_REQUIRES_VALUE' using errcode = '23514';
    end if;
    insert into public.prescription_fields (
      organization_id, prescription_id, schema_id, field_path, field_type, array_item_id,
      original_value, current_value, review_status, confidence, evidence, validation
    ) values (
      target.organization_id, target.id, target.schema_id,
      target_array_path || '[' || next_index || ']', item_definition ->> 'type', item_id,
      null, item_values -> 'value', 'HIGH', null,
      jsonb_build_array(jsonb_build_object('source', 'manual_review')),
      jsonb_build_object('valid', true, 'warnings', '[]'::jsonb, 'reviewed_by', auth.uid())
    ) returning * into created_field;
    insert into public.corrections (
      organization_id, prescription_id, prescription_field_id, old_value, new_value,
      corrected_by, reason
    ) values (
      target.organization_id, target.id, created_field.id, null,
      created_field.current_value, auth.uid(), 'Added repeatable value during review'
    );
    return next created_field;
    return;
  end if;

  for field_record in select key, value from jsonb_each(item_definition) loop
    insert into public.prescription_fields (
      organization_id, prescription_id, schema_id, field_path, field_type, array_item_id,
      original_value, current_value, review_status, confidence, evidence, validation
    ) values (
      target.organization_id, target.id, target.schema_id,
      target_array_path || '[' || next_index || '].' || field_record.key,
      field_record.value ->> 'type', item_id, null, item_values -> field_record.key,
      'HIGH', null, jsonb_build_array(jsonb_build_object('source', 'manual_review')),
      jsonb_build_object('valid', true, 'warnings', '[]'::jsonb, 'reviewed_by', auth.uid())
    ) returning * into created_field;
    insert into public.corrections (
      organization_id, prescription_id, prescription_field_id, old_value, new_value,
      corrected_by, reason
    ) values (
      target.organization_id, target.id, created_field.id, null,
      created_field.current_value, auth.uid(), 'Added repeatable row during review'
    );
    return next created_field;
  end loop;
end;
$$;

create function public.remove_prescription_array_item(
  target_prescription_id uuid,
  target_array_item_id text
)
returns setof public.prescription_fields
language plpgsql
security definer
set search_path = public
as $$
declare
  target public.prescriptions;
  field_row public.prescription_fields;
begin
  select * into target from public.prescriptions where id = target_prescription_id;
  if target is null then raise exception 'PRESCRIPTION_NOT_FOUND' using errcode = 'P0002'; end if;
  if not public.is_org_member(target.organization_id) then raise exception 'ACCESS_DENIED' using errcode = '42501'; end if;
  for field_row in
    select * from public.prescription_fields
    where prescription_id = target.id and array_item_id = target_array_item_id for update
  loop
    insert into public.corrections (
      organization_id, prescription_id, prescription_field_id, old_value, new_value,
      corrected_by, reason
    ) values (
      target.organization_id, target.id, field_row.id, field_row.current_value, 'null'::jsonb,
      auth.uid(), 'Removed repeatable row during review'
    );
    update public.prescription_fields
    set current_value = 'null'::jsonb,
        review_status = 'HIGH',
        validation = jsonb_build_object('valid', true, 'warnings', '[]'::jsonb, 'reviewed_by', auth.uid())
    where id = field_row.id returning * into field_row;
    return next field_row;
  end loop;
  if not found then raise exception 'ARRAY_ITEM_NOT_FOUND' using errcode = 'P0002'; end if;
end;
$$;

grant execute on function public.add_prescription_array_item(uuid, text, jsonb) to authenticated;
grant execute on function public.remove_prescription_array_item(uuid, text) to authenticated;

create or replace function public.approve_prescription_snapshot(
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
  if jsonb_typeof(approved_snapshot) <> 'object' then raise exception 'INVALID_SNAPSHOT' using errcode = '23514'; end if;
  if exists (select 1 from public.prescription_fields where prescription_id = target.id and review_status = 'REVIEW_REQUIRED') then
    raise exception 'UNRESOLVED_REVIEW_FIELDS' using errcode = '23514';
  end if;
  if exists (
    with expected as (
      select field_path as path, current_value as leaf
      from public.prescription_fields field
      where prescription_id = target.id
        and not (
          field.array_item_id is not null and not exists (
            select 1 from public.prescription_fields sibling
            where sibling.prescription_id = field.prescription_id
              and sibling.array_item_id = field.array_item_id
              and sibling.current_value is distinct from 'null'::jsonb
              and sibling.current_value is not null
          )
        )
        and not (
          field.field_type in ('array', 'medicine_list') and field.array_item_id is null
          and exists (
            select 1 from public.prescription_fields child
            where child.prescription_id = field.prescription_id
              and child.field_path like field.field_path || '[%'
              and child.current_value is distinct from 'null'::jsonb
          )
        )
    ), actual as (select * from public.flatten_jsonb(approved_snapshot))
    select 1 from expected full join actual using (path)
    where expected.path is null or actual.path is null or expected.leaf is distinct from actual.leaf
  ) then
    raise exception 'SNAPSHOT_FIELD_MISMATCH' using errcode = '23514';
  end if;
  select * into schema_row from public.prescription_schemas where id = target.schema_id;
  select coalesce(max(version), 0) + 1 into next_version from public.prescription_versions where prescription_id = target.id;
  insert into public.prescription_versions (
    organization_id, prescription_id, schema_id, schema_version, version,
    structured_json, status, created_by
  ) values (
    target.organization_id, target.id, target.schema_id, schema_row.version, next_version,
    approved_snapshot, 'APPROVED', auth.uid()
  ) returning * into approved;
  update public.prescriptions set status = 'APPROVED', approved_at = now(), approved_by = auth.uid()
  where id = target.id;
  return approved;
end;
$$;

commit;
