# Implementation Status

## Current Priority

P0-P3 implementation, Supabase deployment/bootstrap, native OCR, and live structured LLM extraction
are verified; authenticated browser E2E is in progress. All thirteen P4 items were explicitly
requested and are now implemented in the backend, each inert by default where it depends on an
external provider. The reviewer UI has not yet been extended to expose them.

## Completed

- [x] Complete PRD read and exact source copy preserved in `PRD.md`.
- [x] P0 FastAPI + React/TypeScript/Tailwind skeleton, structured configuration/errors, docs.
- [x] P0 Supabase schema, constraints, indexes, triggers, RLS, private buckets, signed storage.
- [x] P0 Supabase Auth login/logout, backend bearer validation, membership-scoped organizations.
- [x] P0 foundation APIs and privileged-secret separation.
- [x] P1 file validation for PDF/JPG/JPEG/PNG, hashing, duplicate protection, private source paths.
- [x] P1 multi-page PDF rendering and supplemental text-layer preservation.
- [x] P1 deterministic quality analysis and selective preprocessing with recorded operations.
- [x] P1 Tesseract abstraction/tokens and pluggable HTR with safe `HTR_NOT_CONFIGURED` behavior.
- [x] P1 processing jobs, safe error states, signed previews, raw OCR API and reviewer UI.
- [x] P2 dynamic schema CRUD/version activation, nested objects, scalar/object arrays, medicines.
- [x] P2 OpenRouter structured-output adapter, timeout/retry, strict non-invention prompt/JSON parser.
- [x] P2 evidence-aware mapper, schema/type/date/enum validation, review status without fake confidence.
- [x] P2 side-by-side reviewer workspace, repeatable row add/remove, evidence/status display.
- [x] P2 append-only correction audit, preserved original/current values, approval safety gate.
- [x] P2 pinned immutable approval snapshot and approved-only final JSON.
- [x] P3 idempotent/resumable processing, duplicate prevention, transient OpenRouter retry.
- [x] P3 JSON request logging without medical text/tokens, safe diagnostics and timings.
- [x] P3 signed-URL/upload/security hardening and frontend secret/dependency audits.
- [x] P3 schema-version pinning, approved-only integration contract, metrics, pagination/query limits.
- [x] All six migrations applied to Supabase project `kyhawltjzllhhcygyevh` through MCP and verified.
- [x] Database hardening: zero anonymous function execution, all 34 foreign keys indexed, optimized RLS init plans.
- [x] First confirmed user bootstrapped as admin of `Prescription OCR Clinic` with active `general_opd` schema.
- [x] Tesseract 5.4 installed/configured; native adapter smoke test recognized prescription text at 95.6% average confidence.
- [x] OpenRouter credentials/model verified with a live strict-schema extraction request.
- [x] Frontend public Supabase configuration generated deterministically without exposing the service-role key.
- [x] README setup, architecture, verification, API surface, and extension documentation.
- [x] P4 `HMISConnector` destination abstraction with a safe inert `HMIS_NOT_CONFIGURED` default.
- [x] P4 `MedikunjMapper` from the dynamic approved snapshot to `patients`, `prescriptions`, and
      `prescription_items`, with the medicine section located by schema type rather than by name.
- [x] P4 non-invention guarantees: uncovered paths reported as `unmapped`, uncoercible values
      reported rather than guessed, unmappable medicine rows refusing the whole dispatch.
- [x] P4 Medikunj PostgREST transport with transient retry and `medimind_id_map` idempotency keyed
      on `pse:{prescription_id}:v{approved_version}`.
- [x] P4 approved-only, membership-scoped `hmis-preview`/`hmis-dispatch` APIs and `hmis/health`.
- [x] P4 connector documentation, `.env.example` keys, and integration contract mapping tables.
- [x] P4 provider benchmark harness (CER/WER/latency/calibration) with a labelled-dataset loader
      and `python -m app.services.benchmark` CLI; failing providers are scored, not fatal.
- [x] P4 PaddleOCR adapter behind `OCR_PROVIDER`, lazily imported and inert without the extra.
- [x] P4 TrOCR handwriting adapter behind `HTR_PROVIDER`, emitting no fabricated boxes and
      confidence only from real generation scores.
- [x] P4 cloud OCR adapters for Google Vision and Azure Document Intelligence, with bounded
      polling, transient retry, and keys held as `SecretStr`.
- [x] P4 automatic schema detection ranking an organization's schemas against raw OCR text and
      refusing to suggest on low signal or ambiguity; suggestion only, never auto-activation.
- [x] P4 medicine dictionary assistance with a bundled seed formulary, deployment override, and
      an explicit "unknown" verdict instead of snapping to the nearest string.
- [x] P4 immutable versioned prompts with pinned digests, recorded per extraction run
      (`prompt_version`/`prompt_sha256` migration) and exposed read-only.
- [x] P4 approved-only feedback dataset export (JSON and JSONL) carrying proposed vs approved
      values and evidence, with reviewer identity excluded.
- [x] P4 multi-stage approvals: data-defined stage chains, in-order sign-off, role checks,
      distinct-reviewer enforcement, and an approval gate on the immutable version.
- [x] P4 bounded background worker pool with key idempotency, saturation backpressure, recorded
      failures, and async processing/status endpoints.
- [x] P4 realtime SSE progress stream with monotonic stage progress, heartbeats, and a bounded
      lifetime.
- [x] P4 FHIR R4 EMR connector reusing the same approved-only mapping, with conditional-create
      idempotency and `OperationOutcome` error detection.

## In Progress

- [ ] None in the codebase.

## Remaining

- [ ] Run local `supabase db reset` / pgTAP when Docker and the Supabase CLI are available.
- [ ] Run the complete A–S acceptance dataset through native Tesseract.
- [ ] Complete the authenticated browser E2E after interactive sign-in.
- [ ] Point `HMIS_PROVIDER`/`EMR_PROVIDER` at a real Medikunj project and FHIR server and run a
      live dispatch; both connectors are verified only against scripted transport doubles.
- [ ] Apply migrations `202608150007_prompt_versioning.sql` and
      `202608150008_multi_stage_approvals.sql` to the live Supabase project.
- [ ] Install the optional `paddle` / `trocr` extras and run the benchmark against the real
      handwriting corpus; the adapters are verified only against stubbed model surfaces.
- [ ] Supply cloud OCR credentials to exercise Google Vision / Azure Document Intelligence live.
- [ ] Expose the P4 assistance, approval, progress, and dispatch surfaces in the reviewer UI;
      P4 is backend-only so far and the frontend is unchanged.

## Blockers

- The current machine has no Docker; live Supabase access is configured through MCP.
- Interactive sign-in is required before the protected browser workflow can be exercised.

These are deployment inputs, not unimplemented code paths. Live Supabase and native OCR are now
verified; the complete authenticated E2E still requires interactive account sign-in and a test
prescription input.

## Tests

- Backend: 254 passed, 1 pre-existing failure
  (`test_p2_dynamic_review.py::test_llm_failure_keeps_manual_null_fields_available`, reproduced at
  commit `f1fde8d` in a clean worktree and unrelated to P4); Ruff clean across all P4 modules;
  configuration and native Tesseract health checks passed.
- P4 suites (218 tests): HMIS connector 19, benchmark 13, PaddleOCR 12, TrOCR 11, cloud OCR 17,
  schema detection 18, medicine assistance 23, prompt versioning 16, feedback dataset 15,
  multi-stage approvals 23, worker pool 18, realtime progress 14, EMR connector 19.
- Benchmark end-to-end: real Tesseract scored 3.1% CER / 16.7% WER on a rendered fixture and
  ranked above the unconfigured HTR engine, which was recorded as a failure rather than crashing.
- API contracts: 44 unique non-HEAD method/path contracts, all distinct.
- Frontend: 5 passed across 3 files; TypeScript, ESLint, and production Vite build passed.
- Supabase migrations: all migration and pgTAP SQL files parse as PostgreSQL; static RLS/private
  bucket/append-only policy assertions passed; all six live migrations and schema checks passed.
- Security: frontend privileged-secret scan passed; npm audit reports 0 vulnerabilities.
- P1/P2/P3 services: corruption, multipage rendering, deterministic preprocessing, HTR fallback,
  alternate schemas, unsupported medicine safety, LLM failure/retry, idempotency, and approved-only
  integration cases passed.
- Live E2E: pending the external runtime items above.

## Last Verified

2026-08-15 (Asia/Calcutta)
