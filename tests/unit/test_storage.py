"""SQLite foundation: migrations, constraints, and assessment persistence."""

from __future__ import annotations

import sqlite3

import pytest

from aurora import DISPLAY_VERSION
from aurora.config.loader import default_config
from aurora.errors import StorageError
from aurora.storage.database import Database
from aurora.storage.repository import AssessmentRepository, utc_now_iso
from aurora.storage.schema import SCHEMA_VERSION


@pytest.fixture()
def database(tmp_path):
    db = Database(tmp_path / "aurora.db")
    db.initialize()
    yield db
    db.close()


def _assessment(db: Database, name: str = "lab assessment"):
    repository = AssessmentRepository(db.connect())
    return repository.create(
        name=name,
        operator="0x7f3a",
        profile="safe",
        aurora_version=DISPLAY_VERSION,
        platform="Linux x86_64",
        config=default_config(),
    )


def test_initialize_reports_current_schema_version(database):
    assert database.schema_version() == SCHEMA_VERSION == 1
    assert database.require_initialized() == 1


def test_all_core_tables_exist(database):
    rows = database.connect().execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    tables = {row["name"] for row in rows}
    assert {
        "assessments",
        "scope_targets",
        "assets",
        "observations",
        "findings",
        "evidence",
        "module_runs",
        "errors",
    } <= tables


def test_initialize_is_idempotent(database):
    assert database.initialize() == SCHEMA_VERSION
    assert database.initialize() == SCHEMA_VERSION


def test_newer_schema_is_refused(tmp_path):
    db = Database(tmp_path / "future.db")
    db.connect().execute(f"PRAGMA user_version = {SCHEMA_VERSION + 5}")
    with pytest.raises(StorageError) as excinfo:
        db.initialize()
    assert "newer" in str(excinfo.value)
    db.close()


def test_uninitialised_database_is_reported(tmp_path):
    db = Database(tmp_path / "empty.db")
    with pytest.raises(StorageError) as excinfo:
        db.require_initialized()
    assert "aurora init" in str(excinfo.value)
    db.close()


def test_context_manager_requires_initialisation(tmp_path):
    db = Database(tmp_path / "empty.db")
    with pytest.raises(StorageError):
        with db:
            pass
    db.close()


def test_in_memory_database_works():
    db = Database.in_memory()
    try:
        assert db.initialize() == SCHEMA_VERSION
        assert db.schema_version() == SCHEMA_VERSION
    finally:
        db.close()


def test_foreign_keys_cascade_with_assessment(database):
    connection = database.connect()
    record = _assessment(database)
    connection.execute(
        """
        INSERT INTO scope_targets
            (assessment_id, kind, scheme, host, port, path_prefix, created_at)
        VALUES (?, 'include', 'https', 'lab.test', 443, '/', ?)
        """,
        (record.id, utc_now_iso()),
    )
    connection.commit()
    assert connection.execute("SELECT COUNT(*) FROM scope_targets").fetchone()[0] == 1

    connection.execute("DELETE FROM assessments WHERE id = ?", (record.id,))
    connection.commit()
    assert connection.execute("SELECT COUNT(*) FROM scope_targets").fetchone()[0] == 0


def test_severity_constraint_rejects_unknown_value(database):
    connection = database.connect()
    record = _assessment(database)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO findings
                (public_id, assessment_id, module, check_id, title, description,
                 severity, confidence, verification, created_at, updated_at)
            VALUES ('AUR-1', ?, 'headers', 'HDR-01', 't', 'd',
                    'catastrophic', 'high', 'CONFIRMED', ?, ?)
            """,
            (record.id, utc_now_iso(), utc_now_iso()),
        )


def test_verification_state_constraint(database):
    connection = database.connect()
    record = _assessment(database)
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO findings
                (public_id, assessment_id, module, check_id, title, description,
                 severity, confidence, verification, created_at, updated_at)
            VALUES ('AUR-2', ?, 'headers', 'HDR-01', 't', 'd',
                    'low', 'high', 'PROBABLY', ?, ?)
            """,
            (record.id, utc_now_iso(), utc_now_iso()),
        )


def test_evidence_requires_a_parent(database):
    connection = database.connect()
    with pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO evidence (kind, content, sha256, created_at)
            VALUES ('snippet', 'x', 'deadbeef', ?)
            """,
            (utc_now_iso(),),
        )


def test_assessment_round_trip(database):
    record = _assessment(database, "customer portal")
    repository = AssessmentRepository(database.connect())

    fetched = repository.get(record.id)
    assert fetched is not None
    assert fetched.name == "customer portal"
    assert fetched.status == "created"
    assert fetched.config()["profile"] == "safe"
    assert repository.count() == 1
    assert [item.id for item in repository.list()] == [record.id]


def test_repository_rejects_blank_name(database):
    repository = AssessmentRepository(database.connect())
    with pytest.raises(StorageError):
        repository.create(
            name="   ",
            operator="0x7f3a",
            profile="safe",
            aurora_version=DISPLAY_VERSION,
            platform="Linux x86_64",
            config=default_config(),
        )


def test_repository_returns_none_for_missing_assessment(database):
    repository = AssessmentRepository(database.connect())
    assert repository.get(999) is None


def test_utc_timestamp_format():
    stamp = utc_now_iso()
    assert stamp.endswith("Z")
    assert "T" in stamp
    assert len(stamp) == 20
