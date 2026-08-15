# PRD — Intelligent Prescription OCR / HTR Digitalization Platform

**Version:** 2.0  
**Status:** Codex Execution Ready  
**Primary OCR Engine:** Tesseract  
**Handwriting Layer:** Pluggable HTR Engine  
**AI Intelligence Layer:** OpenRouter  
**Backend:** Python + FastAPI  
**Frontend:** React + TypeScript + Tailwind CSS  
**Database / Auth / Storage:** Supabase  
**Core Output:** Dynamic structured JSON + reviewer-approved Digital Prescription  

---

# 0. CODEX EXECUTION CONTRACT

This file is the implementation source of truth.

Codex must execute this PRD **strictly in priority order**:

```text
P0 → P1 → P2 → P3
```

Do not implement P4 unless explicitly requested.

## Mandatory execution rules

1. Finish P0 before starting P1.
2. Finish P1 before starting P2.
3. Finish P2 before starting P3.
4. Do not skip a priority because a later feature is easier.
5. Do not redesign the architecture unless a requirement is technically impossible.
6. Keep OCR, HTR, OpenRouter, schema mapping, validation, review, and persistence as separate modules.
7. Do not hardcode prescription fields.
8. Do not hardcode demo OCR outputs or JSON results.
9. Do not fabricate confidence values.
10. Do not allow AI to invent medical content.
11. Preserve original document, raw OCR/HTR, AI output, reviewer corrections, and approved result.
12. Use Supabase migrations for all database changes.
13. Enable Row Level Security on all exposed application tables.
14. Keep Supabase service-role credentials server-side only.
15. Keep OpenRouter secrets server-side only.
16. Keep prescription Storage buckets private.
17. Add automated tests for every completed priority.
18. Do not advance until current-priority acceptance criteria pass.
19. Maintain `IMPLEMENTATION_STATUS.md`.
20. After each priority run:
   - backend tests,
   - frontend tests/type-check,
   - linting,
   - migration validation,
   - RLS/security tests,
   - update `IMPLEMENTATION_STATUS.md`.

## Command to give Codex

> Read `PRD.md` completely. Execute the implementation according to the P0 → P1 → P2 → P3 priorities. Do not proceed to the next priority until the current priority acceptance criteria and tests pass. Keep `IMPLEMENTATION_STATUS.md` updated after every major task.

---

# 1. PRODUCT OVERVIEW

Build an end-to-end prescription digitization platform for:

- handwritten prescriptions,
- scanned prescriptions,
- photographed prescriptions,
- mixed printed + handwritten prescription templates,
- image-based PDFs,
- PDFs where visible text cannot be copied directly.

The system must produce:

1. original source preservation,
2. visible raw OCR/HTR text,
3. OCR/HTR evidence,
4. schema-driven structured JSON,
5. reviewer-editable prescription fields,
6. reviewer-approved final digital prescription,
7. data suitable for Supabase persistence and HMIS/EMR/API integration.

The system is a **transcription and digitization platform**, not an autonomous prescribing system.

---

# 2. PROBLEM STATEMENT

Prescription data is often difficult to digitize because of:

- handwriting,
- poor scans,
- image-only PDFs,
- different hospital/doctor templates,
- mobile photographs,
- rotation/skew,
- low contrast,
- printed labels mixed with handwritten values,
- changing field requirements.

OCR alone only answers:

> What text appears to be present?

The application must also determine:

> What does this text mean?

and:

> Which configured field does it belong to?

---

# 3. CORE PRODUCT FLOW

```text
Prescription PDF / Image
        ↓
Authentication + Authorization
        ↓
Private Source Storage
        ↓
Data Ingestion
        ↓
PDF / Image Processing
        ↓
Quality Analysis
        ↓
Selective Preprocessing
        ↓
Tesseract OCR + Pluggable HTR
        ↓
Canonical Raw Evidence
        ↓
Visible Raw OCR / HTR Text
        ↓
OpenRouter
        +
Dynamic Prescription Schema
        ↓
Dynamic Field Mapper
        ↓
Structured JSON
        ↓
Validation + Review Status
        ↓
Human Review / Correction
        ↓
Approval
        ↓
Versioned Digital Prescription
        ↓
Supabase Postgres
        +
HMIS / EMR / API
```

---

# 4. NON-NEGOTIABLE ARCHITECTURE PRINCIPLES

## 4.1 Original prescription is the source of truth

Never replace the source document with AI-generated content.

## 4.2 OCR is not field extraction

Keep these modules independent:

```text
OCR / HTR
OpenRouter extraction
Dynamic field mapping
Validation
Review
Approval
Persistence
```

## 4.3 Dynamic field architecture

The number of fields is not fixed.

A prescription schema may contain:

```text
10 fields
40 fields
100+ fields
nested objects
repeatable arrays
medicines[]
investigations[]
advice[]
custom fields
```

Changing the schema must not require OCR code changes.

## 4.4 Human review for uncertainty

Medication-related ambiguity must become:

```text
REVIEW_REQUIRED
```

not an AI guess.

## 4.5 Evidence preservation

Where available, retain:

- page,
- source text,
- bounding box,
- OCR/HTR provider,
- confidence,
- document linkage.

---

# 5. USERS AND ROLES

## Reviewer

Can:

- upload prescriptions,
- view source,
- run processing,
- view raw OCR/HTR,
- inspect dynamic fields,
- edit fields,
- add/remove repeatable rows,
- inspect warnings/evidence,
- approve when authorized.

## Admin

Can additionally:

- manage schemas,
- configure providers/settings,
- manage organization-level configuration,
- inspect processing diagnostics.

Minimum roles:

```text
admin
reviewer
```

Future roles may include:

```text
doctor
approver
integration_service
```

---

# 6. SUPPORTED INPUT TYPES

| Input | Handling |
|---|---|
| Digital PDF | Detect usable text layer and preserve it as supplemental evidence |
| Image-based PDF | Render pages to images and run OCR/HTR |
| Scanned PDF | Render, quality-check, preprocess, OCR/HTR |
| JPG/JPEG/PNG | Load as source page |
| Mobile photo | Support rotation, perspective, contrast, denoise |
| Mixed template | Process printed and handwritten content from same page |

---

# 7. HIGH-LEVEL ARCHITECTURE

```text
┌─────────────────────────────────────┐
│ User / Reviewer                     │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│ React Review UI                     │
│ Upload • Preview • OCR • Fields     │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│ FastAPI Backend                     │
│ Auth • APIs • Orchestration         │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│ Data Ingestion                      │
│ Validate • Store • Route • Render   │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│ Quality + Preprocessing             │
└──────────────────┬──────────────────┘
                   ↓
        ┌──────────┴──────────┐
        ↓                     ↓
┌───────────────┐     ┌────────────────┐
│ Tesseract OCR │     │ HTR Engine     │
│ Printed text  │     │ Handwriting    │
└───────┬───────┘     └────────┬───────┘
        └──────────┬───────────┘
                   ↓
┌─────────────────────────────────────┐
│ OCR/HTR Normalizer                  │
│ text • page • bbox • confidence     │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│ Raw Evidence / Raw Text             │
│ Visible in reviewer UI              │
└──────────────────┬──────────────────┘
                   ↓
        ┌──────────┴──────────┐
        ↓                     ↓
┌────────────────┐   ┌─────────────────────┐
│ OpenRouter LLM │   │ Dynamic Schema      │
└───────┬────────┘   │ Supabase JSONB      │
        │            └──────────┬──────────┘
        └──────────┬────────────┘
                   ↓
┌─────────────────────────────────────┐
│ Dynamic Field Mapper                │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│ Structured JSON                     │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│ Validation + Review Status          │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│ Reviewer Workspace                  │
└──────────────────┬──────────────────┘
                   ↓
┌─────────────────────────────────────┐
│ Approved Digital Prescription       │
└──────────────────┬──────────────────┘
                   ↓
      ┌────────────┼────────────┐
      ↓            ↓            ↓
 Supabase DB   Storage     HMIS/EMR/API
```

---

# 8. SUPABASE INTEGRATION

Supabase replaces the earlier MVP SQLite/local-storage persistence approach.

Use Supabase for:

- PostgreSQL,
- authentication,
- private object storage,
- Row Level Security,
- organization ownership,
- dynamic schema storage,
- OCR/HTR persistence,
- correction history,
- approval snapshots,
- processing metadata.

FastAPI remains the processing/orchestration backend.

---

# 9. SUPABASE AUTH

Use Supabase Auth for authenticated sessions.

MVP:

```text
email + password
```

Frontend responsibilities:

- login/logout,
- session handling,
- retrieve user access token.

Backend responsibilities:

- validate authenticated requests,
- validate organization membership,
- perform privileged processing.

Never expose:

```text
SUPABASE_SERVICE_ROLE_KEY
OPENROUTER_API_KEY
```

to the browser.

---

# 10. ORGANIZATION-BASED ACCESS

All prescription data belongs to an organization.

Recommended core tables:

```text
organizations
profiles
organization_members
```

`organization_members` defines user role within an organization.

All organization-owned data queries and mutations must enforce membership.

---

# 11. SUPABASE RLS

Enable RLS on every exposed application table.

Required behavior:

- user A from organization A cannot read organization B prescription data,
- reviewer can access only authorized organization data,
- admin schema operations are organization-scoped,
- frontend filtering is not considered sufficient authorization.

Add indexes to columns used heavily by RLS policies.

---

# 12. SUPABASE STORAGE

Use private buckets.

Recommended buckets:

```text
prescription-source
prescription-derived
```

## Source bucket

Stores original upload.

Path:

```text
{organization_id}/{prescription_id}/original/{generated_filename}
```

## Derived bucket

Stores:

- rendered pages,
- preprocessed pages,
- optional thumbnails.

Paths:

```text
{organization_id}/{prescription_id}/pages/page-001-original.png
{organization_id}/{prescription_id}/pages/page-001-processed.png
```

Rules:

- never overwrite originals,
- no public unrestricted URLs,
- use authenticated/signed access for preview,
- all objects map to organization + prescription.

---

# 13. SUPABASE DATABASE SCHEMA

Use UUID primary keys.

## organizations

```text
id uuid PK
name text
created_at timestamptz
updated_at timestamptz
```

## profiles

```text
id uuid PK -> auth.users.id
display_name text
created_at timestamptz
updated_at timestamptz
```

## organization_members

```text
id uuid PK
organization_id uuid FK
user_id uuid FK -> auth.users.id
role text
created_at timestamptz
```

Unique:

```text
organization_id + user_id
```

## prescription_schemas

```text
id uuid PK
organization_id uuid FK
schema_key text
name text
version integer
definition jsonb
status text
is_active boolean
created_by uuid
created_at timestamptz
updated_at timestamptz
```

## prescriptions

```text
id uuid PK
organization_id uuid FK
uploaded_by uuid FK
schema_id uuid FK
original_filename text
source_mime_type text
source_storage_path text
source_type text
status text
page_count integer
approved_at timestamptz null
approved_by uuid null
created_at timestamptz
updated_at timestamptz
```

## prescription_pages

```text
id uuid PK
organization_id uuid FK
prescription_id uuid FK
page_number integer
original_image_path text
processed_image_path text null
width integer
height integer
quality_metadata jsonb
preprocessing_applied jsonb
status text
created_at timestamptz
updated_at timestamptz
```

Unique:

```text
prescription_id + page_number
```

## ocr_results

```text
id uuid PK
organization_id uuid FK
prescription_id uuid FK
page_id uuid FK
provider text
provider_version text null
raw_text text
confidence numeric null
processing_ms integer
metadata jsonb
created_at timestamptz
```

## ocr_tokens

```text
id uuid PK
organization_id uuid FK
prescription_id uuid FK
page_id uuid FK
ocr_result_id uuid FK
text text
confidence numeric null
bbox jsonb null
sequence_index integer
source text
created_at timestamptz
```

## extraction_runs

```text
id uuid PK
organization_id uuid FK
prescription_id uuid FK
schema_id uuid FK
provider text
model text
input_hash text
raw_response jsonb null
structured_output jsonb null
status text
processing_ms integer
error_code text null
created_at timestamptz
```

Do not store API keys.

## prescription_fields

```text
id uuid PK
organization_id uuid FK
prescription_id uuid FK
schema_id uuid FK
field_path text
field_type text
array_item_id text null
original_value jsonb
current_value jsonb
review_status text
confidence numeric null
evidence jsonb null
validation jsonb null
created_at timestamptz
updated_at timestamptz
```

Examples:

```text
patient.name
clinical.diagnosis
medicines[0].medicine_name
medicines[0].frequency
```

## corrections

Append-only audit history.

```text
id uuid PK
organization_id uuid FK
prescription_id uuid FK
prescription_field_id uuid FK
old_value jsonb
new_value jsonb
corrected_by uuid FK
reason text null
created_at timestamptz
```

## prescription_versions

Approved snapshots.

```text
id uuid PK
organization_id uuid FK
prescription_id uuid FK
version integer
structured_json jsonb
status text
created_by uuid
created_at timestamptz
```

## processing_jobs

```text
id uuid PK
organization_id uuid FK
prescription_id uuid FK
stage text
status text
attempt integer
started_at timestamptz
completed_at timestamptz null
processing_ms integer null
error_code text null
safe_error_message text null
metadata jsonb
created_at timestamptz
updated_at timestamptz
```

---

# 14. REQUIRED INDEXES

At minimum:

```text
organization_members(user_id)
organization_members(organization_id)

prescriptions(organization_id)
prescriptions(status)
prescriptions(created_at)

prescription_pages(prescription_id)

ocr_results(prescription_id)
ocr_tokens(prescription_id)
ocr_tokens(page_id)

prescription_fields(prescription_id)
prescription_fields(field_path)

corrections(prescription_id)

processing_jobs(prescription_id)
processing_jobs(status)

prescription_schemas(organization_id, is_active)
```

---

# 15. DATA INGESTION PIPELINE

The ingestion layer stops at OCR/HTR-ready pages.

It must not perform clinical interpretation.

```text
UPLOAD
  ↓
AUTHENTICATE
  ↓
AUTHORIZE ORGANIZATION
  ↓
VALIDATE FILE
  ↓
GENERATE PRESCRIPTION UUID
  ↓
STORE ORIGINAL IN PRIVATE SUPABASE STORAGE
  ↓
CREATE prescriptions ROW
  ↓
DETECT FILE TYPE
  ↓
┌─────────────────────┬─────────────────────┐
│ PDF                 │ IMAGE               │
↓                     ↓
Check text layer       Load source page
↓
Render if required
└──────────────┬────────────────────────────┘
               ↓
CREATE prescription_pages
               ↓
QUALITY ANALYSIS
               ↓
SELECTIVE PREPROCESSING
               ↓
STORE DERIVED PAGE
               ↓
UPDATE PAGE METADATA
               ↓
OCR_READY
```

---

# 16. INGESTION OUTPUT CONTRACT

```json
{
  "prescription_id": "uuid",
  "organization_id": "uuid",
  "source_type": "pdf",
  "source_storage_path": "...",
  "pages": [
    {
      "page_id": "uuid",
      "page_number": 1,
      "original_image_path": "...",
      "processed_image_path": "...",
      "quality": {
        "blur_score": 58.3,
        "skew_angle": 3.8,
        "low_contrast": true
      },
      "preprocessing_applied": [
        "deskew",
        "contrast_enhancement"
      ],
      "status": "OCR_READY"
    }
  ]
}
```

---

# 17. FILE VALIDATION

Validate:

- extension,
- MIME type,
- file readability,
- corruption,
- configured maximum size,
- configured maximum page count.

Generate object filenames server-side.

Do not execute uploaded files.

---

# 18. IMAGE QUALITY ANALYSIS

Analyze:

- blur,
- brightness,
- contrast,
- skew,
- orientation,
- dimensions,
- resolution.

Output recommendations, not a fixed preprocessing recipe.

---

# 19. SELECTIVE PREPROCESSING

Supported operations:

- orientation correction,
- deskew,
- grayscale,
- denoise,
- contrast enhancement,
- adaptive threshold,
- Otsu threshold,
- resize,
- cautious sharpening,
- perspective correction.

Rules:

1. Preserve original.
2. Record applied operations.
3. Store processed output separately.
4. Fallback safely when preprocessing fails.
5. Same input + same config should be deterministic.

---

# 20. OCR / HTR LAYER

Use provider abstractions.

```text
OCREngine
HTREngine
```

Downstream code must not depend on provider response shape.

---

# 21. TESSERACT

Primary OCR engine.

Use for:

- printed template labels,
- typed patient information,
- hospital headers,
- printed doctor information,
- clean machine-printed text.

Persist:

- raw text,
- token coordinates where available,
- confidence where available,
- provider/version,
- timing.

---

# 22. HTR ENGINE

Separate replaceable interface.

Expected responsibility:

- handwritten medicine,
- handwritten dosage,
- frequency,
- duration,
- instructions,
- diagnosis,
- notes,
- follow-up.

The existing source documents define HTR as pluggable and do not lock one provider.

Therefore implement:

- HTR interface,
- configuration,
- provider health check,
- canonical normalization,
- failure handling,
- test adapter.

If handwriting is requested and no provider is configured:

```text
HTR_NOT_CONFIGURED
```

Do not crash the printed OCR path.

---

# 23. CANONICAL OCR / HTR EVIDENCE

Normalize all providers to:

```json
{
  "text": "Augmentin 625 mg",
  "confidence": 0.91,
  "page": 1,
  "bbox": {
    "x1": 425,
    "y1": 735,
    "x2": 810,
    "y2": 790
  },
  "source": "htr",
  "engine": "provider_name",
  "prescription_id": "uuid",
  "page_id": "uuid"
}
```

Confidence may be `null`.

Never invent it.

---

# 24. RAW OCR / HTR UI

Raw extracted text must remain visible after AI extraction.

Reviewer must be able to compare:

```text
Original Document
Raw OCR / HTR
Mapped Fields
Validation
Evidence
```

Raw results must remain available if OpenRouter fails.

---

# 25. OPENROUTER LAYER

OpenRouter performs semantic understanding.

Input:

```text
Canonical OCR / HTR Evidence
+
Merged Raw Text
+
Active Dynamic Prescription Schema
+
Extraction Rules
```

Output:

```text
Schema-compatible structured JSON
```

Implement:

```text
LLMProvider
  └── OpenRouterProvider
```

Configurable:

- model,
- temperature,
- timeout,
- max tokens,
- retry policy.

`OPENROUTER_API_KEY` is backend-only.

---

# 26. OPENROUTER EXTRACTION RULES

Prompt must enforce:

1. Extract only supported information.
2. Never invent medicine names.
3. Never infer missing dose.
4. Never invent frequency.
5. Never invent duration.
6. Never create unsupported diagnosis.
7. Return null when uncertain.
8. Preserve repeatable medicine records.
9. Associate medicine attributes only when evidence supports association.
10. Respect active JSON schema.
11. Do not provide medical recommendations.
12. Return machine-consumable JSON.

---

# 27. DYNAMIC PRESCRIPTION SCHEMA

Stored in Supabase `prescription_schemas.definition`.

Example:

```json
{
  "schema_key": "general_opd",
  "version": 1,
  "sections": [
    {
      "key": "patient",
      "type": "object",
      "fields": [
        {"key": "name", "type": "string", "required": true},
        {"key": "age", "type": "number", "required": false}
      ]
    },
    {
      "key": "medicines",
      "type": "array",
      "repeatable": true,
      "item_schema": {
        "medicine_name": {"type": "string"},
        "strength": {"type": "string"},
        "dosage": {"type": "string"},
        "frequency": {"type": "string"},
        "duration": {"type": "string"},
        "route": {"type": "string"},
        "instructions": {"type": "string"}
      }
    }
  ]
}
```

Supported field types:

```text
string
number
date
boolean
enum
object
array
medicine_list
key_value
free_text
```

---

# 28. DYNAMIC FIELD MAPPER

Responsibilities:

- read active schema,
- map OpenRouter result,
- build nested objects,
- build repeatable arrays,
- enforce field paths,
- preserve missing/null values,
- normalize allowed types,
- attach evidence,
- create reviewable field records,
- construct structured JSON.

Never assume a fixed field count.

---

# 29. STRUCTURED JSON

Example only:

```json
{
  "patient": {
    "name": "Rahul Sharma"
  },
  "clinical": {
    "chief_complaint": "Fever sore throat"
  },
  "medicines": [
    {
      "medicine_name": "Augmentin",
      "strength": "625 mg",
      "frequency": "1-0-1",
      "duration": "5 days",
      "instructions": "After food"
    }
  ],
  "investigations": ["CBC", "CRP"],
  "follow_up": "5 days"
}
```

Final structure is always defined by the active schema.

---

# 30. VALIDATION

After mapping, validate:

- schema conformity,
- required fields,
- type correctness,
- dates,
- numbers,
- enums,
- nested structures,
- repeated medicine records,
- evidence availability,
- medicine attribute association.

Do not silently modify medical content to make validation pass.

---

# 31. REVIEW STATUS

Use:

```text
HIGH
MEDIUM
LOW
REVIEW_REQUIRED
```

Signals may include:

- OCR/HTR confidence,
- image quality,
- evidence availability,
- OpenRouter uncertainty,
- validation result,
- schema mismatch,
- missing required field.

Do not create fake numeric confidence.

---

# 32. REVIEWER WORKSPACE

Required layout:

```text
┌───────────────────────────────┬───────────────────────────────┐
│ Original Prescription         │ Dynamic Fields                │
│                               │                               │
│ PDF/Image                     │ Patient                       │
│ Zoom                          │ Clinical                      │
│ Page navigation               │ Medicines[]                   │
│ Evidence highlight            │ Any schema-defined fields     │
├───────────────────────────────┼───────────────────────────────┤
│ Raw OCR / HTR                 │ Validation / Status           │
│ Provider + page + text        │ Warnings + missing values     │
└───────────────────────────────┴───────────────────────────────┘
```

Reviewer can:

- edit fields,
- add missing values,
- clear wrong values,
- add/remove repeatable rows,
- view evidence,
- save correction,
- approve prescription.

---

# 33. CORRECTIONS

Never destroy original machine value.

Field:

```json
{
  "original_value": "Augm?ntin",
  "current_value": "Augmentin"
}
```

Audit:

```json
{
  "old_value": "Augm?ntin",
  "new_value": "Augmentin",
  "corrected_by": "uuid"
}
```

Corrections are append-only.

---

# 34. APPROVAL AND VERSIONING

Approval creates an approved snapshot in `prescription_versions`.

Downstream systems must consume:

```text
approved version
```

not raw OpenRouter output.

A later schema edit must not silently change a previously processed/approved prescription.

---

# 35. PROCESSING STATES

```text
UPLOADED
VALIDATING_FILE
REGISTERING_DOCUMENT
ROUTING_FILE
RENDERING
ANALYZING_IMAGE
PREPROCESSING
OCR_READY
OCR_RUNNING
HTR_RUNNING
EXTRACTION_RUNNING
FIELD_MAPPING
VALIDATING
REVIEW_REQUIRED
APPROVED
COMPLETED
```

Failures:

```text
UPLOAD_FAILED
AUTHORIZATION_FAILED
STORAGE_FAILED
RENDER_FAILED
PREPROCESSING_FAILED
OCR_FAILED
HTR_FAILED
HTR_NOT_CONFIGURED
LLM_FAILED
MAPPING_FAILED
VALIDATION_FAILED
DATABASE_FAILED
```

---

# 36. FASTAPI API

All organization-owned endpoints require authentication and authorization.

```http
POST /api/prescriptions
POST /api/prescriptions/{id}/process
GET  /api/prescriptions/{id}
GET  /api/prescriptions/{id}/status
GET  /api/prescriptions/{id}/ocr
GET  /api/prescriptions/{id}/fields
PATCH /api/prescriptions/{id}/fields/{field_id}
PATCH /api/prescriptions/{id}/fields
POST /api/prescriptions/{id}/approve
GET  /api/prescriptions/{id}/json

GET  /api/prescription-schemas
POST /api/prescription-schemas
GET  /api/prescription-schemas/{id}
PUT  /api/prescription-schemas/{id}
POST /api/prescription-schemas/{id}/activate
```

---

# 37. FRONTEND MODULES

```text
AuthGate
OrganizationSelector
PrescriptionUploader
PrescriptionProcessingPage
PrescriptionViewer
RawOCRPanel
DynamicFieldPanel
DynamicFieldRenderer
MedicineListEditor
EvidenceOverlay
ConfidenceBadge
ValidationPanel
ProcessingStatus
ReviewActions
SchemaManager
```

---

# 38. REPOSITORY STRUCTURE

```text
project/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   ├── core/
│   │   ├── services/
│   │   │   ├── ingestion/
│   │   │   ├── pdf/
│   │   │   ├── preprocessing/
│   │   │   ├── ocr/
│   │   │   ├── htr/
│   │   │   ├── llm/
│   │   │   ├── extraction/
│   │   │   ├── schema/
│   │   │   ├── validation/
│   │   │   ├── confidence/
│   │   │   ├── review/
│   │   │   └── storage/
│   │   ├── models/
│   │   ├── repositories/
│   │   │   └── supabase/
│   │   └── tests/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── features/
│   │   ├── lib/
│   │   │   ├── supabase.ts
│   │   │   └── api.ts
│   │   └── types/
│   └── package.json
├── supabase/
│   ├── migrations/
│   ├── seed.sql
│   └── config.toml
├── docs/
├── PRD.md
├── IMPLEMENTATION_STATUS.md
├── README.md
└── .env.example
```

---

# 39. ENVIRONMENT VARIABLES

```text
SUPABASE_URL=
SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SERVICE_ROLE_KEY=

OPENROUTER_API_KEY=
OPENROUTER_MODEL=

TESSERACT_CMD=
HTR_PROVIDER=
HTR_MODEL=

MAX_UPLOAD_MB=
MAX_PDF_PAGES=

VITE_SUPABASE_URL=
VITE_SUPABASE_PUBLISHABLE_KEY=
VITE_API_BASE_URL=
```

Rules:

- `.env` is gitignored.
- `.env.example` contains variable names only.
- Service role never enters frontend bundle.
- OpenRouter key never enters frontend bundle.

---

# 40. OBSERVABILITY

Durably record processing stage and timing.

Useful metadata:

- prescription ID,
- organization ID,
- stage,
- page,
- OCR provider,
- HTR provider,
- preprocessing applied,
- OpenRouter model,
- timing,
- validation warnings,
- safe error code.

Do not unnecessarily log full medical text.

Never log secrets/tokens.

---

# 41. MEDICAL SAFETY BOUNDARY

Never:

- prescribe,
- recommend treatment,
- substitute medicine,
- invent medicine,
- infer unsupported diagnosis,
- silently change dosage,
- silently change frequency,
- silently change duration,
- convert ambiguous handwriting into a confident value.

When uncertain:

```json
{
  "value": null,
  "review_status": "REVIEW_REQUIRED"
}
```

---

# 42. ERROR HANDLING

## File failure

Stop before OCR and preserve specific error state.

## Storage failure

Set:

```text
STORAGE_FAILED
```

## OCR failure

Preserve original and report:

```text
OCR_FAILED
```

## HTR unavailable

Report:

```text
HTR_NOT_CONFIGURED
```

Printed OCR may continue.

## OpenRouter failure

- apply configured retry,
- keep raw OCR/HTR,
- set `LLM_FAILED`,
- permit manual review.

## Invalid JSON

Only deterministic syntax repair is allowed.

Do not invent semantic content.

## Partial extraction

Accept partial output.

Missing fields become:

```text
null + review flag
```

---

# 43. TEST DATASET

| ID | Scenario |
|---|---|
| A | Clean printed prescription |
| B | Clear handwritten prescription |
| C | Difficult handwriting |
| D | Image-based template PDF |
| E | Rotated/skewed scan |
| F | Low contrast |
| G | Mobile photo |
| H | Five+ medicines |
| I | Missing fields |
| J | Multi-page prescription |
| K | Alternate dynamic schema |
| L | Corrupt file |
| M | OpenRouter failure |
| N | Invalid JSON |
| O | Cross-org unauthorized access |
| P | Private Storage access denied |
| Q | Correction audit |
| R | Approval snapshot |
| S | HTR not configured |

---

# 44. METRICS

## OCR / HTR

- CER,
- WER,
- text coverage.

## Field extraction

- exact match,
- precision,
- recall,
- missing-field rate.

## Medication association

- medicine name accuracy,
- strength accuracy,
- dosage accuracy,
- frequency accuracy,
- duration accuracy,
- instruction association accuracy.

## Operational

- render time,
- preprocessing time,
- OCR time,
- HTR time,
- OpenRouter time,
- total time,
- review rate,
- correction rate.

## Safety

Unsupported/invented accepted medical values are a critical defect.

Target:

```text
0 accepted unsupported values
```

---

# 45. PRIORITY PLAN

# P0 — FOUNDATION / SUPABASE / SECURITY

**Blocking priority.**

## P0.1 Project skeleton

- FastAPI backend,
- React/TypeScript/Tailwind frontend,
- Supabase configuration,
- config/error system,
- `.env.example`,
- README,
- `IMPLEMENTATION_STATUS.md`.

## P0.2 Database migrations

Create all tables defined in this PRD.

Add:

- foreign keys,
- indexes,
- timestamps,
- constraints.

## P0.3 RLS

Enable and test organization-scoped RLS.

Tests must prove:

- cross-org read denied,
- cross-org mutation denied,
- reviewer access works,
- admin schema access works.

## P0.4 Auth

Implement:

- login,
- logout,
- protected frontend,
- backend token validation,
- organization membership loading.

## P0.5 Private Storage

Create:

```text
prescription-source
prescription-derived
```

Implement private upload and preview access.

## P0.6 Foundation APIs

```http
GET /health
GET /api/me
GET /api/organizations
GET /api/prescription-schemas
```

## P0 Definition of Done

- clean migrations work,
- auth works,
- organization loads,
- RLS blocks cross-org access,
- private Storage works,
- no service secret is exposed,
- P0 tests pass.

---

# P1 — DATA INGESTION + OCR

## P1.1 Upload API

Implement:

```http
POST /api/prescriptions
```

Flow:

```text
auth
→ authorize
→ validate
→ UUID
→ private Storage
→ prescriptions row
```

## P1.2 PDF/image handling

- detect format,
- inspect PDF text layer,
- render scanned/image pages,
- support multi-page,
- register pages.

## P1.3 Quality analyzer

Persist quality metadata.

## P1.4 Selective preprocessing

Apply only required processing.

Store derived images separately.

## P1.5 Tesseract

Implement provider abstraction and normalized evidence.

Persist raw text/tokens/timing.

## P1.6 HTR abstraction

Implement interface/config/health/error behavior.

## P1.7 Normalizer

Create canonical OCR/HTR evidence.

## P1.8 Raw OCR API

```http
GET /api/prescriptions/{id}/ocr
```

## P1.9 Processing state

Persist transitions in `processing_jobs`.

## P1.10 Frontend

Implement:

- upload,
- processing status,
- source preview,
- raw OCR panel.

## P1 Definition of Done

- PDF/JPG/PNG upload works,
- image-only PDF renders,
- original preserved,
- page lineage correct,
- preprocessing tracked,
- Tesseract OCR visible in UI,
- OCR persisted,
- HTR degrades safely,
- P1 tests pass.

---

# P2 — OPENROUTER / DYNAMIC FIELDS / REVIEW

## P2.1 Schema Registry

Full CRUD for dynamic schemas.

Must support:

- nested object,
- array,
- repeatable medicines,
- required/optional,
- validators.

## P2.2 OpenRouter provider

Implement:

- model config,
- timeout,
- retry,
- JSON handling,
- timing,
- error state.

## P2.3 Extraction prompt

Use:

```text
OCR/HTR + evidence + active schema + safety rules
```

## P2.4 Extraction runs

Persist OpenRouter execution metadata.

## P2.5 Dynamic mapper

Generate:

- nested JSON,
- review fields,
- arrays,
- evidence links.

## P2.6 Validation

Implement schema + medical safety validation.

## P2.7 Review status

Generate HIGH/MEDIUM/LOW/REVIEW_REQUIRED.

## P2.8 Reviewer workspace

Full side-by-side UI.

## P2.9 Corrections

Persist original/current and append audit history.

## P2.10 Approval

Create approved snapshot.

## P2.11 Final JSON

```http
GET /api/prescriptions/{id}/json
```

returns approved version.

## P2 Definition of Done

- second schema works without OCR edits,
- OpenRouter uses active schema,
- dynamic nested JSON generated,
- repeatable medicines work,
- uncertain values are not invented,
- reviewer edits work,
- corrections are audited,
- approval snapshot exists,
- final JSON retrievable,
- P2 tests pass.

---

# P3 — HARDENING / OPERATIONS / INTEGRATION

## P3.1 Reliability

- idempotent processing,
- retry policy,
- duplicate protection,
- recoverable states,
- job abstraction.

## P3.2 Observability

- structured logging,
- timings,
- error categories,
- admin diagnostics.

## P3.3 Security hardening

- RLS review,
- signed URL expiry,
- upload limits,
- secret audit,
- audit coverage.

## P3.4 Schema versioning

Pin processing to exact schema version.

## P3.5 HMIS/EMR-ready integration contract

Only approved prescription data can be exported.

Possible endpoint:

```http
GET /api/prescriptions/{id}/integration-payload
```

Future adapter:

```text
PrescriptionDestination
├── HMIS
├── EMR
└── Generic Webhook
```

## P3.6 Analytics

Basic metrics:

- processed count,
- OCR failures,
- LLM failures,
- review-required rate,
- correction rate,
- average processing time.

## P3.7 Performance

- pagination,
- indexed filters,
- optimized token loading,
- query limits,
- avoid unnecessary full OCR-token fetches.

## P3 Definition of Done

- retry/idempotency tested,
- schema version pinned,
- safe failure recovery,
- secrets reviewed,
- RLS reviewed,
- integration contract documented,
- metrics available,
- P3 tests pass.

---

# P4 — OPTIONAL FUTURE WORK

Do not implement before P0-P3.

Potential future items:

- concrete advanced HTR provider benchmark,
- PaddleOCR adapter,
- TrOCR adapter,
- cloud OCR adapters,
- automatic schema detection,
- medicine dictionary reviewer assistance,
- prompt versioning,
- advanced feedback dataset,
- multi-stage approvals,
- background worker pool,
- realtime progress,
- production HMIS connector,
- production EMR connector.

---

# 46. IMPLEMENTATION STATUS FILE

Codex must create:

```markdown
# Implementation Status

## Current Priority
P0

## Completed
- [x] ...

## In Progress
- [ ] ...

## Remaining
- [ ] ...

## Blockers
- None

## Tests
- Backend:
- Frontend:
- Supabase migrations:
- RLS:
- E2E:

## Last Verified
timestamp
```

---

# 47. CODING RULES

## Backend

- typed Pydantic models,
- modular services,
- repository/service separation,
- provider abstractions,
- no giant `main.py`,
- structured errors.

## Frontend

- TypeScript,
- reusable dynamic field renderer,
- no hardcoded prescription form,
- accessible controls,
- enterprise review layout,
- proper loading/error/empty states.

## Supabase

- migrations committed,
- RLS committed,
- indexes committed,
- no dashboard-only schema changes.

## Tests

Unit:

- preprocessing,
- mapper,
- validators,
- OpenRouter parsing,
- auth helpers.

Integration:

- Supabase repositories,
- Storage,
- APIs,
- processing states.

E2E:

```text
login
→ upload
→ process
→ raw OCR
→ dynamic extraction
→ review
→ correction
→ approval
→ final JSON
```

---

# 48. ACCEPTANCE CRITERIA

## Document handling

- PDF/JPG/JPEG/PNG supported.
- Multi-page PDF supported.
- Original preserved.
- Page lineage preserved.

## Supabase

- Auth works.
- Organization access works.
- RLS isolates organizations.
- Storage is private.
- Migrations recreate schema.
- No privileged secret in frontend.

## OCR

- Tesseract output captured.
- Raw OCR visible.
- Evidence persisted where available.

## HTR

- provider abstraction exists.
- no-provider case fails gracefully.
- configured provider can emit canonical evidence.

## OpenRouter

- raw evidence + schema submitted.
- structured response handled.
- failure preserves raw evidence.
- key never exposed.

## Dynamic mapping

- no fixed field count.
- nested fields supported.
- repeatable medicine records supported.
- alternate schema works without OCR code change.

## Review

- fields editable.
- original values preserved.
- corrections append history.
- evidence inspectable.

## Safety

- uncertain medication content requires review.
- unsupported values are not silently accepted.

## Finalization

- approval works.
- approved version is stored.
- final JSON is retrievable.
- downstream payload uses approved output only.

---

# 49. DEFINITION OF DONE

The project is complete when:

1. Fresh clone setup is documented.
2. Supabase migrations apply from clean state.
3. User can authenticate.
4. Cross-org access is blocked.
5. Prescription uploads to private Storage.
6. Image-based PDF is rendered.
7. Preprocessing works and is recorded.
8. Tesseract runs.
9. Raw OCR is visible.
10. HTR interface is operational/configurable.
11. OpenRouter processes raw evidence + active schema.
12. Dynamic mapping generates JSON.
13. Second schema works without OCR changes.
14. Reviewer can correct fields.
15. Correction history is preserved.
16. Approval creates versioned final snapshot.
17. Final JSON can be retrieved.
18. Failure states are explicit.
19. Automated tests pass.
20. No backend secret appears in frontend/logs.
21. README documents setup, Supabase, migrations, architecture, tests, and extension points.
22. `IMPLEMENTATION_STATUS.md` is current.

---

# 50. FINAL ARCHITECTURE RULE

Do not reduce the system to:

```text
Document → LLM → Trust Result
```

The architecture must remain:

```text
Original Source
→ Data Ingestion
→ OCR / HTR
→ Raw Evidence
→ OpenRouter Understanding
→ Dynamic Schema Mapping
→ Structured JSON
→ Validation
→ Human Review
→ Approved Version
→ Supabase / HMIS / EMR / API
```

The reviewer-approved prescription is authoritative for downstream use.

---

# 51. FINAL INSTRUCTION TO CODEX

Execute this PRD as an implementation plan.

Start with **P0** only.

When P0 tests and acceptance criteria pass, continue to **P1**.

Then **P2**.

Then **P3**.

Do not implement P4 unless explicitly requested.

After each major task and every priority boundary, update `IMPLEMENTATION_STATUS.md`.

Do not collapse modules, do not hardcode fields, do not expose secrets, and do not allow AI-generated medical values to bypass human review when uncertain.
