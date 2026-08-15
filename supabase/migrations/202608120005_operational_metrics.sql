begin;

create function public.organization_processing_metrics(target_organization_id uuid)
returns jsonb
language plpgsql
stable
security definer
set search_path = public
as $$
declare
  result jsonb;
begin
  if not public.is_org_member(target_organization_id) then
    raise exception 'ACCESS_DENIED' using errcode = '42501';
  end if;
  select jsonb_build_object(
    'processed_count', (select count(*) from public.prescriptions where organization_id = target_organization_id),
    'ocr_failures', (select count(*) from public.processing_jobs where organization_id = target_organization_id and error_code in ('OCR_FAILED', 'OCR_NOT_CONFIGURED')),
    'llm_failures', (select count(*) from public.processing_jobs where organization_id = target_organization_id and error_code in ('LLM_FAILED', 'LLM_NOT_CONFIGURED', 'LLM_INVALID_JSON')),
    'review_required_count', (select count(*) from public.prescriptions where organization_id = target_organization_id and status in ('REVIEW_REQUIRED', 'LLM_FAILED')),
    'approved_count', (select count(*) from public.prescriptions where organization_id = target_organization_id and status = 'APPROVED'),
    'correction_count', (select count(*) from public.corrections where organization_id = target_organization_id),
    'average_processing_ms', (select coalesce(round(avg(processing_ms)), 0) from public.processing_jobs where organization_id = target_organization_id and processing_ms is not null)
  ) into result;
  return result;
end;
$$;

revoke all on function public.organization_processing_metrics(uuid) from public, anon;
grant execute on function public.organization_processing_metrics(uuid) to authenticated;

commit;

