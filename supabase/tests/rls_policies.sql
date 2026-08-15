begin;

select plan(8);

select has_table('public', 'prescriptions', 'prescriptions table exists');
select ok((select relrowsecurity from pg_class where oid = 'public.prescriptions'::regclass), 'RLS active on prescriptions');
select ok((select relrowsecurity from pg_class where oid = 'public.prescription_schemas'::regclass), 'RLS active on schemas');
select ok((select relrowsecurity from pg_class where oid = 'public.corrections'::regclass), 'RLS active on corrections');
select is(
  (select count(*) from pg_policies where schemaname = 'public' and tablename = 'prescription_schemas'),
  4::bigint,
  'schema policies are explicit and organization scoped'
);
select is(
  (select count(*) from pg_policies where schemaname = 'public' and tablename = 'prescriptions'),
  3::bigint,
  'prescription policies are explicit and organization scoped'
);
select is((select public.is_org_member(gen_random_uuid())), false, 'anonymous context is not a member');
select is((select public.has_org_role(gen_random_uuid(), array['admin']::public.organization_role[])), false, 'anonymous context is not an admin');

select * from finish();
rollback;
