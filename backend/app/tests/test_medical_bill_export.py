import json
from uuid import UUID, uuid4

import pytest

from app.services.export.excel import generate_excel_export
from app.services.schema.detection import SchemaDetector
from app.services.schema.registry import SchemaRegistry
from app.services.schema.templates import GENERAL_OPD_SCHEMA, MEDICAL_BILL_SCHEMA
from app.tests.conftest import ORG_ID

SAMPLE_BILL_JSON = {
    "provider": {
        "hospital_name": "Apollo Pharmacy & Healthcare",
        "doctor_name": "Dr. S. K. Sharma",
        "bill_number": "INV-2026-9812",
        "bill_date": "2026-08-15",
        "tax_id": "07AAAAA0000A1Z5",
        "contact_number": "+91 98765 43210",
    },
    "patient": {
        "name": "Amit Verma",
        "patient_id": "UHID-88219",
        "age": "35",
        "gender": "Male",
    },
    "medicines": [
        {
            "medicine_name": "Augmentin 625mg Tab",
            "unique_code": "HSN3004 / BATCH-B491",
            "unit_price": 204.50,
            "quantity": 2,
            "discount": 10.0,
            "tax_rate": 12.0,
            "total_price": 399.00,
        },
        {
            "medicine_name": "Pan 40mg Tab",
            "unique_code": "BATCH-P021",
            "unit_price": 145.00,
            "quantity": 1,
            "discount": 0.0,
            "tax_rate": 12.0,
            "total_price": 145.00,
        },
    ],
    "billing_summary": {
        "subtotal": 554.00,
        "discount_total": 10.00,
        "tax_amount": 58.20,
        "total_cost": 544.00,
        "payment_mode": "UPI / Google Pay",
        "payment_status": "PAID",
    },
}

BILL_RAW_OCR = """
APOLLO PHARMACY & HEALTHCARE
Tax Invoice / Cash Memo
Bill No: INV-2026-9812  Date: 15-08-2026
Doctor: Dr. S. K. Sharma  GSTIN: 07AAAAA0000A1Z5
Patient Name: Amit Verma  UHID: UHID-88219  Age: 35  Gender: Male

Item Name                  Batch/Code    Rate    Qty   Disc   Amount
1. Augmentin 625mg Tab     BATCH-B491    204.50  2     10.0   399.00
2. Pan 40mg Tab            BATCH-P021    145.00  1     0.0    145.00

Subtotal: 554.00
Discount: 10.00
Total Tax / GST: 58.20
Grand Total / Net Payable: 544.00
Payment Mode: UPI (PAID)
"""


def test_medical_bill_schema_is_valid():
    registry = SchemaRegistry()
    validated = registry.validate(MEDICAL_BILL_SCHEMA)
    assert validated["schema_key"] == "medical_bill"
    json_schema = registry.to_json_schema(MEDICAL_BILL_SCHEMA)
    assert "provider" in json_schema["properties"]
    assert "billing_summary" in json_schema["properties"]
    assert json_schema["properties"]["medicines"]["items"]["properties"]["unit_price"]


def test_schema_detector_identifies_medical_bill_from_ocr_text():
    schemas = [
        {"id": "s1", "schema_key": "general_opd", "name": "Prescription", "is_active": True, "definition": GENERAL_OPD_SCHEMA},
        {"id": "s2", "schema_key": "medical_bill", "name": "Medical Bill", "is_active": True, "definition": MEDICAL_BILL_SCHEMA},
    ]
    report = SchemaDetector().detect(BILL_RAW_OCR, schemas)
    assert report.candidates[0].schema_key == "medical_bill"
    assert report.suggested_schema_id == "s2"
    assert report.confident is True
    assert "pharmacy" in report.candidates[0].matched_terms or "bill" in report.candidates[0].matched_terms or "total" in report.candidates[0].matched_terms


def test_generate_excel_export_creates_valid_xlsx_bytes():
    excel_bytes = generate_excel_export(
        structured_json=SAMPLE_BILL_JSON,
        document_name="apollo_bill_sample.pdf",
        document_id="44444444-4444-4444-8444-444444444444",
    )
    assert len(excel_bytes) > 1000
    # Check standard ZIP/XLSX magic bytes (PK\x03\x04)
    assert excel_bytes.startswith(b"PK\x03\x04")


def test_export_endpoints_in_api(client, repository):
    test_id = UUID("44444444-4444-4444-8444-444444444444")

    async def prescription_for_user(prescription_id):
        return {
            "id": str(test_id),
            "organization_id": str(ORG_ID),
            "original_filename": "medical_receipt_101.pdf",
            "schema_id": str(uuid4()),
        }

    async def fields_for_user(prescription_id):
        return [
            {
                "id": str(uuid4()),
                "field_path": "patient.name",
                "field_type": "string",
                "current_value": "Amit Verma",
                "review_status": "HIGH",
            },
            {
                "id": str(uuid4()),
                "field_path": "billing_summary.total_cost",
                "field_type": "number",
                "current_value": 544.0,
                "review_status": "HIGH",
            },
        ]

    async def approved_version(prescription_id):
        return {"structured_json": SAMPLE_BILL_JSON}

    repository.prescription_for_user = prescription_for_user
    repository.fields_for_user = fields_for_user
    repository.approved_version = approved_version

    # Test JSON export endpoint
    res_json = client.get(f"/api/prescriptions/{test_id}/export/json")
    assert res_json.status_code == 200
    assert res_json.json()["patient"]["name"] == "Amit Verma"
    assert res_json.json()["billing_summary"]["total_cost"] == 544.0

    # Test Excel export endpoint
    res_excel = client.get(f"/api/prescriptions/{test_id}/export/excel")
    assert res_excel.status_code == 200
    assert res_excel.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "medical_receipt_101_export.xlsx" in res_excel.headers["content-disposition"]
    assert res_excel.content.startswith(b"PK\x03\x04")
