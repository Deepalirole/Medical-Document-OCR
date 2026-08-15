from pathlib import Path

import pytest
from pglast import parse_sql

from app.core.errors import AppError
from app.services.storage.supabase import SupabaseStorage

ROOT = Path(__file__).parents[3]
MIGRATIONS = ROOT / "supabase" / "migrations"


def migration_sql() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(MIGRATIONS.glob("*.sql")))


def test_all_application_tables_enable_rls():
    sql = migration_sql()
    tables = {
        "organizations",
        "profiles",
        "organization_members",
        "prescription_schemas",
        "prescriptions",
        "prescription_pages",
        "ocr_results",
        "ocr_tokens",
        "extraction_runs",
        "prescription_fields",
        "corrections",
        "prescription_versions",
        "processing_jobs",
    }
    for table in tables:
        assert f"alter table public.{table} enable row level security;" in sql


def test_every_migration_parses_as_postgresql_sql():
    paths = [
        *sorted(MIGRATIONS.glob("*.sql")),
        *sorted((ROOT / "supabase" / "tests").glob("*.sql")),
    ]
    for path in paths:
        assert parse_sql(path.read_text(encoding="utf-8")), path.name


def test_storage_buckets_are_private_and_scoped():
    sql = migration_sql()
    assert "('prescription-source', 'prescription-source', false" in sql
    assert "('prescription-derived', 'prescription-derived', false" in sql
    assert "public.is_org_member(((storage.foldername(name))[1])::uuid)" in sql


def test_corrections_have_no_update_or_delete_policy():
    sql = migration_sql()
    assert "create policy corrections_insert" in sql
    assert "create policy corrections_update" not in sql
    assert "create policy corrections_delete" not in sql


def test_database_hardening_removes_public_function_access_and_optimizes_rls():
    sql = migration_sql()
    assert (
        "revoke all on function public.handle_new_user() from public, anon, authenticated;" in sql
    )
    assert (
        "revoke all on function public.rls_auto_enable() from public, anon, authenticated;" in sql
    )
    assert "grant execute on function public.approve_prescription_snapshot(uuid, jsonb)" in sql
    assert "id = (select auth.uid())" in sql
    assert "uploaded_by = (select auth.uid())" in sql
    assert "corrected_by = (select auth.uid())" in sql


def test_every_uncovered_foreign_key_has_a_hardening_index():
    sql = migration_sql()
    expected_indexes = {
        "corrections_corrected_by_idx",
        "corrections_organization_idx",
        "corrections_field_idx",
        "extraction_runs_organization_idx",
        "extraction_runs_schema_idx",
        "ocr_results_organization_idx",
        "ocr_results_page_idx",
        "ocr_tokens_organization_idx",
        "prescription_fields_organization_idx",
        "prescription_fields_schema_idx",
        "prescription_pages_organization_idx",
        "prescription_schemas_created_by_idx",
        "prescription_versions_created_by_idx",
        "prescription_versions_organization_idx",
        "prescription_versions_schema_idx",
        "prescriptions_approved_by_idx",
        "prescriptions_schema_idx",
        "prescriptions_uploaded_by_idx",
        "processing_jobs_organization_idx",
    }
    for index_name in expected_indexes:
        assert f"create index if not exists {index_name}" in sql


def test_storage_path_cannot_escape_organization():
    organization_id = "22222222-2222-4222-8222-222222222222"
    safe = f"{organization_id}/prescription/original/source.pdf"
    normalized = SupabaseStorage.validate_object_path(
        "prescription-source", safe, organization_id
    )
    assert normalized == safe
    with pytest.raises(AppError):
        SupabaseStorage.validate_object_path(
            "prescription-source", "other-organization/prescription/source.pdf", organization_id
        )


def test_frontend_does_not_reference_server_secrets():
    frontend = ROOT / "frontend" / "src"
    source = "\n".join(
        path.read_text(encoding="utf-8") for path in frontend.rglob("*") if path.is_file()
    )
    assert "SUPABASE_SERVICE_ROLE_KEY" not in source
    assert "OPENROUTER_API_KEY" not in source
