# Prescription Evidence Studio

An evidence-preserving prescription digitization platform built from the version 2.0 PRD in
[PRD.md](PRD.md). It keeps source documents, OCR/HTR evidence, AI extraction, validation,
reviewer corrections, and approved output as separate, auditable stages.

> Medical safety boundary: this system transcribes documents. It does not prescribe, recommend,
> substitute, or silently infer unsupported medical content. Only reviewer-approved versions are
> eligible for downstream integration.

## Architecture

```text
React + Supabase Auth
        |
        v
FastAPI authorization/orchestration
        |
        +--> Private Supabase Storage (source + derived)
        +--> PDF/image ingestion --> quality --> selective preprocessing
        +--> Tesseract OCR + pluggable HTR --> canonical evidence
        +--> OpenRouter + pinned dynamic schema --> mapper --> validation
        +--> reviewer corrections --> immutable approved version
        `--> Supabase Postgres with organization-scoped RLS
```

The browser receives only the Supabase publishable key. The service-role and OpenRouter keys are
read only by FastAPI.

## Prerequisites

- Python 3.12+
- Node.js 20+
- Supabase project, or Supabase CLI plus Docker for the local stack
- Tesseract executable for real OCR (tests use provider doubles)
- OpenRouter key for semantic extraction (manual review remains available when absent)

## Setup

1. Copy `.env.example` to `.env` and populate the variables. Never commit `.env`.
2. Apply migrations in `supabase/migrations` to a clean Supabase project.
3. Create a user through Supabase Auth, then create an organization and membership. See
   `supabase/seed.sql` for the development pattern.
4. Install and start the backend:

   ```powershell
   cd backend
   python -m pip install -e ".[dev]"
   python -m uvicorn app.main:app --reload
   ```

5. Install and start the frontend in a second terminal:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

## Verification

```powershell
cd backend
python -m pytest
python -m ruff check app

cd ../frontend
npm run typecheck
npm test
npm run lint
npm run build
npm audit --audit-level=moderate
```

Run `supabase test db` and `supabase db reset` when the CLI and Docker are available. SQL-level
RLS assertions live in `supabase/tests/rls_policies.sql`; backend security tests also verify that
every exposed application table enables RLS and both storage buckets remain private.

The local automated gate also parses every migration and pgTAP file as PostgreSQL syntax, verifies
all FastAPI method/path pairs are unique, scans the frontend for privileged secret names, and runs a
production Vite bundle plus dependency audit.

## API surface

- Foundation: `/health`, `/api/me`, `/api/organizations`.
- Schemas: list/create/read/update/delete/activate under `/api/prescription-schemas`.
- Pipeline: upload, process/resume, detail, status, signed preview, and raw OCR under
  `/api/prescriptions`.
- Review: dynamic fields, single/bulk corrections, repeatable row add/remove, approval, final JSON.
- Operations: paginated prescriptions, organization metrics, admin diagnostics.
- Integration: `/api/prescriptions/{id}/integration-payload` exports approved versions only; see
  [docs/INTEGRATION_CONTRACT.md](docs/INTEGRATION_CONTRACT.md).

`Idempotency-Key` is supported by the processing endpoint. Duplicate uploads are also protected by
an organization/source SHA-256 constraint. Failed OCR can resume from persisted derived pages, and
failed LLM extraction leaves raw evidence plus null review fields available for manual completion.

## Extension points

- OCR providers implement `OCREngine` and return canonical evidence.
- HTR providers implement `HTREngine`; an unconfigured provider returns `HTR_NOT_CONFIGURED`
  without breaking printed OCR.
- LLM providers implement `LLMProvider`; OpenRouter is the production adapter.
- Dynamic schemas are data, not form code. Nested objects and arrays are handled by the mapper and
  the React dynamic renderer.
- Downstream destinations consume only immutable approved snapshots.

See [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md) for verified progress and environment
limitations.


Outputs:-

Document review
<img width="1909" height="901" alt="Screenshot 2026-08-15 213017" src="https://github.com/user-attachments/assets/83eb6739-40ee-4214-a692-f96ba86bfa00" />


<img width="1906" height="903" alt="Screenshot 2026-08-15 213026" src="https://github.com/user-attachments/assets/b023b86c-de4a-453e-a60a-6737aa51ce1e" />





