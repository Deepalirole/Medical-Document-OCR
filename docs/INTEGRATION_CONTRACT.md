# Approved Prescription Integration Contract

`GET /api/prescriptions/{id}/integration-payload` is the only P3 export boundary. It returns `409
NOT_APPROVED` until a reviewer-approved immutable version exists. OCR output, OpenRouter output, and
unapproved current fields are never exported.

```json
{
  "contract_version": "1.0",
  "prescription_id": "uuid",
  "organization_id": "uuid",
  "schema": { "id": "uuid", "version": 2 },
  "approved_version": 1,
  "approved_at": "2026-08-12T10:00:00Z",
  "data": {}
}
```

The `data` object is dynamic and is defined by the pinned schema ID/version. Consumers must select
an adapter by schema identity rather than assuming fixed prescription fields. Recommended adapters
implement a `PrescriptionDestination` boundary and reject payloads with unknown contract or schema
versions. No production HMIS/EMR transport is included in P3.

## P4 — Medikunj HMIS/EMR connector

P4 adds a destination boundary on top of the same approved-only contract. Nothing about the P3
export changed; the connector consumes contract version `1.0` and refuses anything else.

```text
Approved snapshot → MedikunjMapper → HMISDocument → HMISConnector → Medikunj HMIS
```

### Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/integrations/hmis/health` | Destination provider, configured flag, status. |
| `GET` | `/api/prescriptions/{id}/hmis-preview` | Mapped destination records, no write. |
| `POST` | `/api/prescriptions/{id}/hmis-dispatch` | Maps and writes to the destination. |

All three require a bearer session, and preview/dispatch additionally assert membership of the
prescription's organization. Dispatch returns `409 NOT_APPROVED` until a reviewer-approved
immutable version exists.

### Mapping

`MedikunjMapper` projects the dynamic approved object onto the fixed Medikunj tables using an
explicit `MedikunjFieldMapping` of destination column to ordered candidate paths:

| Destination | Column | Approved paths |
| --- | --- | --- |
| `patients` | `full_name` | `patient.name`, `patient.full_name`, `patient_name` |
| `patients` | `age_at_reg` | `patient.age`, `patient_age` |
| `patients` | `gender` | `patient.gender`, `patient_gender`, `patient.sex` |
| `patients` | `mobile_number` | `patient.mobile`, `patient.phone`, `patient.contact` |
| `patients` | `address` | `patient.address` |
| `prescriptions` | `notes` | `notes`, `advice`, `remarks`, `instructions` |
| `prescription_items` | `drug_name` | `medicine_name`, `drug_name`, `name` |
| `prescription_items` | `dosage` | `strength`, `dose`, `dosage` |
| `prescription_items` | `frequency` | `frequency`, `timing` |
| `prescription_items` | `duration` | `duration` |
| `prescription_items` | `quantity` | `quantity`, `qty` |
| `prescription_items` | `instructions` | `instructions`, `note`, `remarks` |

The repeatable medicine section is located by schema **type** (`medicine_list`) rather than by
name, so an alternate schema that calls the section `drug_chart` maps without a code change.

Safety rules the mapper enforces:

- Nothing is invented. Every populated column traces to an approved value.
- Approved paths the mapping does not cover are listed in `unmapped`, never silently dropped, and
  the whole approved payload is retained in `medimind_id_map.source_data`.
- A value that cannot be coerced to the destination type is reported as `path:not-coercible` and
  left unset rather than guessed.
- An approved medicine row with no mappable drug name raises `HMIS_MEDICINE_UNMAPPABLE` and the
  whole dispatch is refused.

### Idempotency

Each dispatch derives a deterministic `source_id` of `pse:{prescription_id}:v{approved_version}`.
The connector looks that up in `medimind_id_map` before any write, so replaying an approved version
returns the existing target IDs instead of duplicating clinical rows.

### Configuration

The destination is inert until configured. With `HMIS_PROVIDER` unset, health reports
`HMIS_NOT_CONFIGURED`, preview still works, and dispatch returns `503` — the same pattern the HTR
abstraction uses.

```dotenv
HMIS_PROVIDER=medikunj_supabase
HMIS_BASE_URL=https://your-medikunj-project.supabase.co
HMIS_SERVICE_KEY=service-role-key
HMIS_BRANCH_ID=uuid-of-the-target-branch
HMIS_TIMEOUT_SECONDS=30
HMIS_RETRIES=2
```

`HMIS_SERVICE_KEY` is a `SecretStr`, is never returned by the health endpoint, and never reaches
the frontend.

### Error codes

| Code | Status | Meaning |
| --- | --- | --- |
| `NOT_APPROVED` | 409 | No reviewer-approved version exists. |
| `HMIS_CONTRACT_UNSUPPORTED` | 409 | Payload contract version is not `1.0`. |
| `HMIS_PAYLOAD_INVALID` | 409 | Approved snapshot carries no structured object. |
| `HMIS_MEDICINE_UNMAPPABLE` | 409 | An approved medicine row has no mappable drug name. |
| `HMIS_NOT_CONFIGURED` | 503 | No destination configured. |
| `HMIS_DISPATCH_FAILED` | 502 | Destination rejected or could not be reached. |

### Adding another destination

Implement the `HMISConnector` protocol (`name`, `health`, `async dispatch`) in
`backend/app/services/integrations/`, then return it from `get_hmis_connector` for a new
`HMIS_PROVIDER` value. The mapper, the approved-only gate, and the API surface are unchanged.

## P4 — FHIR EMR connector

The EMR destination reuses the same approved-only path and the same `HMISDocument`, so both
connectors receive an identically mapped payload and only the transport differs.

```text
Approved snapshot → MedikunjMapper → HMISDocument → FHIREMRConnector → FHIR R4 server
```

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/integrations/emr/health` | Destination provider, configured flag, status. |
| `POST` | `/api/prescriptions/{id}/emr-dispatch` | Maps and posts a FHIR transaction bundle. |

### Resources

One `transaction` Bundle per dispatch: a `Patient` followed by one `MedicationRequest` per
approved medicine. `dosageInstruction.text` is assembled from the approved dosage, frequency,
duration, and instruction values, and an absent value is omitted rather than defaulted — a
`Patient` with no approved gender carries no `gender` element, and an out-of-range gender code
is dropped rather than coerced.

### Idempotency

Every resource carries an identifier of `https://prescription-evidence-studio/source-id` with
the deterministic `source_id` (`:{index}` for each medicine), and every entry uses FHIR's
conditional create (`ifNoneExist`). Replaying an approved version therefore resolves to the
existing resources on the server. A response whose entries are all `200` is reported as
`idempotent: true`; `201` entries mean records were created.

### Failure handling

A `200` response carrying an `OperationOutcome` with `error` or `fatal` severity is treated as
a failure, not a success — an EMR that reports problems in the body must not look like a
successful write. Warning-only outcomes pass. Transient statuses (429/5xx) are retried;
permanent rejections raise `EMR_DISPATCH_FAILED` with the status.

### Configuration

```dotenv
EMR_PROVIDER=fhir
EMR_BASE_URL=https://emr.example.test/fhir
EMR_API_KEY=bearer-token
EMR_TIMEOUT_SECONDS=30
EMR_RETRIES=2
```

With `EMR_PROVIDER` unset the connector is inert: health reports `EMR_NOT_CONFIGURED` and
dispatch returns `503`.

| Code | Status | Meaning |
| --- | --- | --- |
| `NOT_APPROVED` | 409 | No reviewer-approved version exists. |
| `EMR_NOT_CONFIGURED` | 503 | No EMR destination configured. |
| `EMR_DISPATCH_FAILED` | 502 | EMR rejected the bundle or could not be reached. |

