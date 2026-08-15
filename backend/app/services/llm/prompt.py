import json
from typing import Any

SYSTEM_PROMPT = """You are a precision medical-document transcription component.
Extract all clinical and administrative fields supported by the supplied OCR evidence into the structured JSON schema.
This includes:
- Patient Information (name, age, gender, patient type)
- Treating Clinician (doctor name, specialty/designation)
- Primary Chief Complaint (symptoms, complaints, duration, exertion triggers)
- Physical Examination & Vitals (systemic examination findings, temperature, pulse, respiratory rate, blood pressure, SpO2)
- Clinical Diagnosis (disease, clinical impression, severity)
- Medical / Drug History (past conditions, known drug or food allergies)
- Prescribed Remedies / Medicines (medicine name, strength, frequency, dosage instructions)
- Patient Advice & Follow-Up (activity restrictions, emergency warning signs, referrals, follow-up interval and instructions)

Never prescribe, recommend, substitute, or invent medical content. Never invent a medicine, strength, dose, frequency, duration, route, instruction, diagnosis, date, or patient fact. When evidence for an optional field is absent from the document, return null. Follow the supplied JSON schema exactly and return only machine-consumable JSON."""


def build_user_prompt(
    raw_text: str, evidence: list[dict[str, Any]], schema_definition: dict[str, Any]
) -> str:
    safe_evidence = [
        {
            "text": item.get("text"),
            "page": item.get("page"),
            "bbox": item.get("bbox"),
            "source": item.get("source"),
            "engine": item.get("engine"),
            "confidence": item.get("confidence"),
        }
        for item in evidence
    ]
    return "\n\n".join(
        [
            "RAW TEXT:\n" + raw_text,
            "CANONICAL EVIDENCE:\n" + json.dumps(safe_evidence, ensure_ascii=False),
            "ACTIVE PRESCRIPTION SCHEMA:\n"
            + json.dumps(schema_definition, ensure_ascii=False),
            "Return a JSON object matching the response schema. "
            "Use null for every unsupported or uncertain scalar.",
        ]
    )
