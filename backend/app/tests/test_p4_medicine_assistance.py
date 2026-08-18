from uuid import uuid4

from app.api.dependencies import get_medicine_dictionary
from app.core.config import Settings
from app.services.assistance.medicines import (
    MedicineDictionary,
    field_matches_medicine_name,
    medicine_name_paths,
    normalize_name,
)
from app.tests.conftest import ORG_ID
from app.tests.test_p2_dynamic_review import PRESCRIPTION_ID, SCHEMA_ID

SMALL = ["Augmentin", "Amoxicillin", "Omeprazole", "Paracetamol", "Losartan", "Lisinopril"]

MEDICINE_SCHEMA = {
    "sections": [
        {"key": "patient", "type": "object", "fields": [{"key": "name", "type": "string"}]},
        {
            "key": "medicines",
            "type": "medicine_list",
            "item_schema": {
                "medicine_name": {"type": "string"},
                "strength": {"type": "string"},
            },
        },
    ]
}


def test_normalization_strips_dose_forms_and_strengths():
    assert normalize_name("Tab. Augmentin-625mg") == "augmentin"
    assert normalize_name("CAP OMEPRAZOLE 20 mg") == "omeprazole"
    assert normalize_name("Syr. Paracetamol") == "paracetamol"
    assert normalize_name("  ") == ""


def test_exact_match_is_reported_as_known():
    lookup = MedicineDictionary(SMALL).lookup("augmentin")
    assert lookup.known is True
    assert lookup.suggestions[0].name == "Augmentin"
    assert lookup.suggestions[0].exact is True
    assert lookup.suggestions[0].score == 1.0


def test_a_dose_form_prefix_still_matches_exactly():
    assert MedicineDictionary(SMALL).lookup("Tab. Augmentin 625mg").known is True


def test_a_misspelling_returns_ranked_candidates_but_is_not_known():
    lookup = MedicineDictionary(SMALL).lookup("Augmentn")
    assert lookup.known is False
    assert lookup.suggestions[0].name == "Augmentin"
    assert lookup.suggestions[0].exact is False
    assert 0.7 < lookup.suggestions[0].score < 1.0


def test_an_unknown_drug_returns_no_suggestions_rather_than_the_nearest_string():
    lookup = MedicineDictionary(SMALL).lookup("Zzyzxidine")
    assert lookup.known is False
    assert lookup.suggestions == []


def test_similar_but_distinct_drugs_are_not_collapsed():
    """Losartan and Lisinopril are different drugs; neither may be reported as known."""
    lookup = MedicineDictionary(SMALL).lookup("Losartan")
    assert lookup.known is True
    assert lookup.suggestions[0].name == "Losartan"
    assert all(s.name != "Lisinopril" for s in lookup.suggestions)


def test_a_large_length_gap_is_treated_as_a_different_drug():
    lookup = MedicineDictionary(["Paracetamol"]).lookup("Par")
    assert lookup.suggestions == []


def test_suggestion_limit_is_respected():
    dictionary = MedicineDictionary(["Amoxicillin", "Amoxicillon", "Amoxicilin", "Amoxycillin"])
    assert len(dictionary.lookup("Amoxicilln", limit=2).suggestions) == 2


def test_empty_query_is_handled_without_suggestions():
    lookup = MedicineDictionary(SMALL).lookup("   ")
    assert lookup.known is False
    assert lookup.normalized_query == ""
    assert lookup.suggestions == []


def test_lookup_payload_always_demands_reviewer_confirmation():
    payload = MedicineDictionary(SMALL).lookup("augmentin").to_dict()
    assert payload["requires_reviewer_confirmation"] is True


def test_bundled_seed_dictionary_loads_and_recognises_common_drugs():
    dictionary = MedicineDictionary()
    assert len(dictionary) > 100
    for name in ("Paracetamol", "Metformin", "Azithromycin", "Pantoprazole"):
        assert dictionary.lookup(name).known is True


def test_a_deployment_dictionary_is_merged_on_top_of_the_seed(tmp_path):
    extra = tmp_path / "local.txt"
    extra.write_text("# local formulary\nHospistat Forte\n\n", encoding="utf-8")
    dictionary = MedicineDictionary(extra_path=extra)
    assert dictionary.lookup("Hospistat Forte").known is True
    assert dictionary.lookup("Paracetamol").known is True


def test_a_missing_dictionary_path_is_ignored_rather_than_fatal(tmp_path):
    dictionary = MedicineDictionary(extra_path=tmp_path / "absent.txt")
    assert len(dictionary) > 100


def test_medicine_name_paths_are_found_by_schema_type():
    assert medicine_name_paths(MEDICINE_SCHEMA) == {"medicines.medicine_name"}
    assert medicine_name_paths({"sections": []}) == set()


def test_medicine_name_paths_handle_alternate_item_key_names():
    schema = {
        "sections": [
            {
                "key": "drug_chart",
                "type": "medicine_list",
                "item_schema": {"drug_name": {"type": "string"}},
            }
        ]
    }
    assert medicine_name_paths(schema) == {"drug_chart.drug_name"}


def test_indexed_field_paths_match_the_schema_signature():
    paths = {"medicines.medicine_name"}
    assert field_matches_medicine_name("medicines[0].medicine_name", paths) is True
    assert field_matches_medicine_name("medicines[12].medicine_name", paths) is True
    assert field_matches_medicine_name("medicines[0].strength", paths) is False
    assert field_matches_medicine_name("patient.name", paths) is False


# --- API -----------------------------------------------------------------------------


def override_dictionary(entries=None):
    from app.main import app

    dictionary = MedicineDictionary(entries if entries is not None else SMALL)
    app.dependency_overrides[get_medicine_dictionary] = lambda: dictionary
    return dictionary


def clear_override():
    from app.main import app

    app.dependency_overrides.pop(get_medicine_dictionary, None)


def test_lookup_endpoint_returns_ranked_candidates(client):
    override_dictionary()
    try:
        response = client.get("/api/assistance/medicines", params={"query": "Augmentn"})
    finally:
        clear_override()
    assert response.status_code == 200
    body = response.json()
    assert body["known"] is False
    assert body["suggestions"][0]["name"] == "Augmentin"
    assert body["requires_reviewer_confirmation"] is True


def test_lookup_endpoint_rejects_an_empty_query(client):
    override_dictionary()
    try:
        response = client.get("/api/assistance/medicines", params={"query": ""})
    finally:
        clear_override()
    assert response.status_code == 422


def wire_prescription(repository, fields, definition=MEDICINE_SCHEMA):
    async def prescription_for_user(_id):
        return {
            "id": str(PRESCRIPTION_ID),
            "organization_id": str(ORG_ID),
            "schema_id": str(SCHEMA_ID),
        }

    async def schema_for_user(_schema_id):
        return {"id": str(SCHEMA_ID), "definition": definition}

    async def fields_for_user(_id):
        return fields

    repository.prescription_for_user = prescription_for_user
    repository.schema_for_user = schema_for_user
    repository.fields_for_user = fields_for_user


def test_prescription_endpoint_only_examines_medicine_name_fields(client, repository):
    wire_prescription(
        repository,
        [
            {"id": "f1", "field_path": "patient.name", "current_value": "Rahul Sharma"},
            {"id": "f2", "field_path": "medicines[0].medicine_name", "current_value": "Augmentn"},
            {"id": "f3", "field_path": "medicines[0].strength", "current_value": "625 mg"},
            {"id": "f4", "field_path": "medicines[1].medicine_name", "current_value": "Omeprazole"},
        ],
    )
    override_dictionary()
    try:
        response = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/medicine-suggestions")
    finally:
        clear_override()

    assert response.status_code == 200
    body = response.json()
    assert body["fields_examined"] == 2
    assert body["unknown_medicines"] == 1
    assert body["requires_reviewer_confirmation"] is True
    paths = [field["field_path"] for field in body["fields"]]
    assert paths == ["medicines[0].medicine_name", "medicines[1].medicine_name"]
    assert body["fields"][0]["known"] is False
    assert body["fields"][0]["suggestions"][0]["name"] == "Augmentin"
    assert body["fields"][1]["known"] is True


def test_prescription_endpoint_ignores_non_string_values(client, repository):
    wire_prescription(
        repository,
        [{"id": "f1", "field_path": "medicines[0].medicine_name", "current_value": None}],
    )
    override_dictionary()
    try:
        response = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/medicine-suggestions")
    finally:
        clear_override()
    assert response.json()["fields_examined"] == 0


def test_prescription_endpoint_is_inert_for_a_schema_without_medicines(client, repository):
    wire_prescription(
        repository,
        [{"id": "f1", "field_path": "investigations[0]", "current_value": "CBC"}],
        definition={"sections": [{"key": "investigations", "type": "array"}]},
    )
    override_dictionary()
    try:
        response = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/medicine-suggestions")
    finally:
        clear_override()
    assert response.json()["fields_examined"] == 0


def test_prescription_endpoint_enforces_membership(client, repository):
    async def foreign(_id):
        return {"id": str(PRESCRIPTION_ID), "organization_id": str(uuid4())}

    repository.prescription_for_user = foreign
    override_dictionary()
    try:
        response = client.get(f"/api/prescriptions/{PRESCRIPTION_ID}/medicine-suggestions")
    finally:
        clear_override()
    assert response.status_code == 403


def test_dictionary_dependency_is_cached_per_configuration():
    first = get_medicine_dictionary(Settings())
    second = get_medicine_dictionary(Settings())
    assert first is second
