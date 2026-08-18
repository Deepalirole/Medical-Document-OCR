-- P4: prompt versioning.
-- Records which immutable extraction prompt produced each run so an extracted value can be
-- traced back to the exact instruction text the model received. Nullable because providers
-- without a versioned prompt must record no lineage rather than a fabricated one.

alter table public.extraction_runs
  add column if not exists prompt_version text,
  add column if not exists prompt_sha256 text;

comment on column public.extraction_runs.prompt_version is
  'Immutable prompt version identifier from app.services.llm.prompt_registry.';
comment on column public.extraction_runs.prompt_sha256 is
  'SHA-256 of the system prompt text actually sent for this run.';

create index if not exists extraction_runs_prompt_version_idx
  on public.extraction_runs(prompt_version);
