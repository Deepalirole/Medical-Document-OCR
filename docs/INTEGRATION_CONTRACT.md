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

