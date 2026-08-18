from pydantic import BaseModel


class PromptVersionModel(BaseModel):
    version: str
    description: str
    sha256: str
    retired: bool
    matches_pin: bool


class PromptVersionsResponse(BaseModel):
    latest: str
    versions: list[PromptVersionModel]


class MedicineSuggestionModel(BaseModel):
    name: str
    score: float
    exact: bool


class MedicineLookupResponse(BaseModel):
    query: str
    normalized_query: str
    known: bool
    requires_reviewer_confirmation: bool
    suggestions: list[MedicineSuggestionModel]


class MedicineFieldSuggestion(MedicineLookupResponse):
    field_id: str
    field_path: str
    value: str


class PrescriptionMedicineSuggestions(BaseModel):
    prescription_id: str
    dictionary_size: int
    fields_examined: int
    unknown_medicines: int
    requires_reviewer_confirmation: bool
    fields: list[MedicineFieldSuggestion]


class SchemaCandidateModel(BaseModel):
    schema_id: str
    schema_key: str
    name: str
    version: int
    is_active: bool
    score: float
    matched_terms: list[str]
    total_terms: int


class SchemaSuggestionResponse(BaseModel):
    suggested_schema_id: str | None
    confident: bool
    margin: float
    active_schema_id: str | None
    reason: str
    signals_considered: int
    requires_reviewer_confirmation: bool
    candidates: list[SchemaCandidateModel]
