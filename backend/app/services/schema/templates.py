"""Standard schema templates for clinical prescriptions and medical bills."""

from typing import Any

GENERAL_OPD_SCHEMA: dict[str, Any] = {
    "schema_key": "general_opd",
    "name": "General OPD Prescription",
    "version": 1,
    "sections": [
        {
            "key": "patient",
            "type": "object",
            "label": "Patient Information",
            "fields": [
                {"key": "name", "type": "string", "required": True, "aliases": ["patient name", "patient", "name"]},
                {"key": "age", "type": "string", "required": False, "aliases": ["age", "yrs"]},
                {"key": "gender", "type": "string", "required": False, "aliases": ["gender", "sex"]},
            ],
        },
        {
            "key": "clinician",
            "type": "object",
            "label": "Treating Clinician",
            "fields": [
                {"key": "doctor_name", "type": "string", "required": False, "aliases": ["doctor", "dr", "physician", "consultant"]},
                {"key": "specialty", "type": "string", "required": False, "aliases": ["specialty", "department", "designation"]},
            ],
        },
        {
            "key": "medicines",
            "type": "medicine_list",
            "label": "Prescribed Medicines",
            "required": True,
            "aliases": ["medicines", "prescribed remedies", "rx", "drugs", "treatment"],
            "item_schema": {
                "medicine_name": {"type": "string", "required": True, "aliases": ["medicine", "drug name", "remedy"]},
                "strength": {"type": "string", "aliases": ["strength", "dosage", "potency", "mg"]},
                "frequency": {"type": "string", "aliases": ["frequency", "timing", "daily", "instructions"]},
                "duration": {"type": "string", "aliases": ["duration", "days", "period"]},
            },
        },
        {
            "key": "diagnosis",
            "type": "object",
            "label": "Clinical Diagnosis & Advice",
            "fields": [
                {"key": "clinical_impression", "type": "string", "required": False, "aliases": ["diagnosis", "impression", "complaint"]},
                {"key": "advice", "type": "string", "required": False, "aliases": ["advice", "instructions", "precautions"]},
                {"key": "follow_up", "type": "string", "required": False, "aliases": ["follow up", "next visit", "review on"]},
            ],
        },
    ],
}

MEDICAL_BILL_SCHEMA: dict[str, Any] = {
    "schema_key": "medical_bill",
    "name": "Medical Bill & Pharmacy Receipt",
    "version": 1,
    "sections": [
        {
            "key": "provider",
            "type": "object",
            "label": "Hospital & Pharmacy Details",
            "fields": [
                {"key": "hospital_name", "type": "string", "required": False, "aliases": ["hospital", "pharmacy", "clinic", "chemist", "center", "store", "medical store", "healthcare"]},
                {"key": "doctor_name", "type": "string", "required": False, "aliases": ["doctor", "consultant", "dr", "prescriber", "physician", "consulting doctor"]},
                {"key": "bill_number", "type": "string", "required": False, "aliases": ["invoice", "bill no", "receipt no", "cash memo", "invoice no", "memo no", "bill number", "receipt"]},
                {"key": "bill_date", "type": "string", "required": False, "aliases": ["date", "receipt date", "invoice date", "bill date", "billing date", "dated"]},
                {"key": "tax_id", "type": "string", "required": False, "aliases": ["gstin", "gst", "tin", "dl no", "license no", "drug license", "reg no"]},
                {"key": "contact_number", "type": "string", "required": False, "aliases": ["phone", "mobile", "tel", "contact", "ph"]},
            ],
        },
        {
            "key": "patient",
            "type": "object",
            "label": "Patient & Customer Details",
            "fields": [
                {"key": "name", "type": "string", "required": True, "aliases": ["patient name", "patient", "customer", "client", "m/s", "mr", "mrs", "patient details"]},
                {"key": "patient_id", "type": "string", "required": False, "aliases": ["uhid", "patient id", "ipd no", "opd no", "mrn", "reg no", "patient code"]},
                {"key": "age", "type": "string", "required": False, "aliases": ["age", "yrs", "years"]},
                {"key": "gender", "type": "string", "required": False, "aliases": ["gender", "sex", "male", "female"]},
            ],
        },
        {
            "key": "medicines",
            "type": "medicine_list",
            "label": "Billed Medicines & Items",
            "required": True,
            "aliases": ["items", "medicines", "drugs", "products", "particulars", "description", "billed items", "item details", "pharmacy items"],
            "item_schema": {
                "medicine_name": {"type": "string", "required": True, "aliases": ["medicine", "item", "product", "drug", "description", "item name", "particulars"]},
                "unique_code": {"type": "string", "aliases": ["unique code", "batch", "batch no", "hsn", "hsn code", "item code", "barcode", "code", "lot"]},
                "unit_price": {"type": "number", "aliases": ["cost", "unit price", "price", "rate", "mrp", "unit cost", "rate/unit"]},
                "quantity": {"type": "number", "aliases": ["qty", "quantity", "units", "count", "packs", "nos"]},
                "discount": {"type": "number", "aliases": ["discount", "disc", "disc %", "less", "scheme"]},
                "tax_rate": {"type": "number", "aliases": ["tax", "gst", "gst %", "vat", "cgst", "sgst"]},
                "total_price": {"type": "number", "aliases": ["amount", "total", "net amount", "item total", "line total", "value", "price"]},
            },
        },
        {
            "key": "billing_summary",
            "type": "object",
            "label": "Financial Summary & Totals",
            "fields": [
                {"key": "subtotal", "type": "number", "required": False, "aliases": ["subtotal", "sub total", "taxable amount", "gross total", "gross amount", "total mrp"]},
                {"key": "discount_total", "type": "number", "required": False, "aliases": ["discount total", "total discount", "overall discount", "total disc"]},
                {"key": "tax_amount", "type": "number", "required": False, "aliases": ["tax amount", "total tax", "gst total", "cgst + sgst", "vat total", "tax"]},
                {"key": "total_cost", "type": "number", "required": True, "aliases": ["total cost", "grand total", "net amount", "total amount", "net payable", "amount payable", "final total", "total", "bill amount", "round off"]},
                {"key": "payment_mode", "type": "string", "required": False, "aliases": ["payment mode", "mode of payment", "cash", "card", "upi", "online", "credit"]},
                {"key": "payment_status", "type": "string", "required": False, "aliases": ["payment status", "paid", "due", "pending", "settled"]},
            ],
        },
    ],
}

DEFAULT_TEMPLATES = {
    "general_opd": GENERAL_OPD_SCHEMA,
    "medical_bill": MEDICAL_BILL_SCHEMA,
}
