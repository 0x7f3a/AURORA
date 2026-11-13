"""SQLite schema and forward-only migrations.

The schema separates what was *observed* from what was *verified*:
``observations`` store facts collected by a module, ``findings`` store claims
that survived verification, and ``evidence`` links raw material to either.

Integrity is enforced by the database where possible: enumerated columns use
``CHECK`` constraints, children cascade with their assessment, and evidence must
belong to either a finding or an observation. Application code still validates
before writing, but the constraints mean a bug cannot silently persist an
invalid severity or an orphaned evidence blob.

Migrations are append-only. Never edit a released migration; add a new one.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["MIGRATIONS", "SCHEMA_VERSION", "Migration"]


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    description: str
    statements: tuple[str, ...]


_INITIAL_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS assessments (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        name            TEXT    NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 200),
        operator        TEXT    NOT NULL CHECK (length(trim(operator)) BETWEEN 1 AND 64),
        profile         TEXT    NOT NULL CHECK (profile IN ('safe')),
        status          TEXT    NOT NULL DEFAULT 'created'
                                CHECK (status IN ('created', 'running', 'completed', 'aborted', 'failed')),
        aurora_version  TEXT    NOT NULL,
        platform        TEXT    NOT NULL,
        config_json     TEXT    NOT NULL,
        notes           TEXT,
        created_at      TEXT    NOT NULL,
        started_at      TEXT,
        finished_at     TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_assessments_created
        ON assessments(created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS scope_targets (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        assessment_id   INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
        kind            TEXT    NOT NULL CHECK (kind IN ('include', 'exclude')),
        scheme          TEXT    NOT NULL CHECK (scheme IN ('http', 'https')),
        host            TEXT    NOT NULL CHECK (length(trim(host)) > 0),
        port            INTEGER NOT NULL DEFAULT 0 CHECK (port BETWEEN 0 AND 65535),
        path_prefix     TEXT    NOT NULL DEFAULT '/',
        note            TEXT,
        created_at      TEXT    NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_scope_targets
        ON scope_targets(assessment_id, kind, scheme, host, port, path_prefix)
    """,
    """
    CREATE TABLE IF NOT EXISTS assets (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        assessment_id   INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
        url             TEXT    NOT NULL,
        scheme          TEXT    NOT NULL,
        host            TEXT    NOT NULL,
        port            INTEGER NOT NULL DEFAULT 0,
        status_code     INTEGER,
        content_type    TEXT,
        content_length  INTEGER,
        body_sha256     TEXT,
        source          TEXT    NOT NULL DEFAULT 'discovery',
        first_seen_at   TEXT    NOT NULL,
        last_seen_at    TEXT    NOT NULL
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_assets_url
        ON assets(assessment_id, url)
    """,
    """
    CREATE TABLE IF NOT EXISTS observations (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        assessment_id   INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
        asset_id        INTEGER REFERENCES assets(id) ON DELETE SET NULL,
        module          TEXT    NOT NULL,
        check_id        TEXT    NOT NULL,
        title           TEXT    NOT NULL,
        detail          TEXT    NOT NULL,
        created_at      TEXT    NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_observations_assessment
        ON observations(assessment_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS findings (
        id                    INTEGER PRIMARY KEY AUTOINCREMENT,
        public_id             TEXT    NOT NULL UNIQUE,
        assessment_id         INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
        asset_id              INTEGER REFERENCES assets(id) ON DELETE SET NULL,
        observation_id        INTEGER REFERENCES observations(id) ON DELETE SET NULL,
        module                TEXT    NOT NULL,
        check_id              TEXT    NOT NULL,
        title                 TEXT    NOT NULL,
        description           TEXT    NOT NULL,
        technical_explanation TEXT,
        impact                TEXT,
        remediation           TEXT,
        limitations           TEXT,
        severity              TEXT    NOT NULL
                                      CHECK (severity IN ('info', 'low', 'medium', 'high', 'critical')),
        confidence            TEXT    NOT NULL
                                      CHECK (confidence IN ('low', 'medium', 'high')),
        verification          TEXT    NOT NULL
                                      CHECK (verification IN ('CONFIRMED', 'POTENTIAL', 'INCONCLUSIVE', 'REJECTED')),
        created_at            TEXT    NOT NULL,
        updated_at            TEXT    NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_findings_assessment
        ON findings(assessment_id, severity)
    """,
    """
    CREATE TABLE IF NOT EXISTS evidence (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        finding_id      INTEGER REFERENCES findings(id) ON DELETE CASCADE,
        observation_id  INTEGER REFERENCES observations(id) ON DELETE CASCADE,
        kind            TEXT    NOT NULL CHECK (kind IN ('request', 'response', 'snippet', 'note')),
        label           TEXT,
        content         TEXT    NOT NULL,
        sha256          TEXT    NOT NULL,
        created_at      TEXT    NOT NULL,
        CHECK (finding_id IS NOT NULL OR observation_id IS NOT NULL)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS module_runs (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        assessment_id   INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
        module          TEXT    NOT NULL,
        module_version  TEXT,
        status          TEXT    NOT NULL
                                CHECK (status IN ('completed', 'skipped', 'failed', 'unavailable', 'not_implemented')),
        reason          TEXT,
        requests_made   INTEGER NOT NULL DEFAULT 0 CHECK (requests_made >= 0),
        started_at      TEXT    NOT NULL,
        finished_at     TEXT
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_module_runs_assessment
        ON module_runs(assessment_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS errors (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        assessment_id   INTEGER NOT NULL REFERENCES assessments(id) ON DELETE CASCADE,
        module          TEXT,
        category        TEXT    NOT NULL,
        message         TEXT    NOT NULL,
        created_at      TEXT    NOT NULL
    )
    """,
)

MIGRATIONS: tuple[Migration, ...] = (
    Migration(version=1, description="initial assessment schema", statements=_INITIAL_SCHEMA),
)

SCHEMA_VERSION: int = MIGRATIONS[-1].version
