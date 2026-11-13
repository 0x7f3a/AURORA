"""Persistence for assessment records.

Only assessments are exposed in this milestone; scope targets, assets,
observations, findings and evidence have schema support but no writer yet,
because the engines that produce them do not exist. Adding repository methods
before those modules would mean guessing their interfaces.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from aurora.config.models import AuroraConfig
from aurora.errors import StorageError

__all__ = ["AssessmentRecord", "AssessmentRepository", "utc_now_iso"]


def utc_now_iso() -> str:
    """Current UTC time as ``YYYY-MM-DDTHH:MM:SSZ``."""

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@dataclass(frozen=True, slots=True)
class AssessmentRecord:
    id: int
    name: str
    operator: str
    profile: str
    status: str
    aurora_version: str
    platform: str
    config_json: str
    notes: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None

    def config(self) -> dict[str, Any]:
        """The configuration snapshot recorded when the assessment was created."""

        parsed = json.loads(self.config_json)
        return parsed if isinstance(parsed, dict) else {}


def _record(row: sqlite3.Row) -> AssessmentRecord:
    return AssessmentRecord(
        id=int(row["id"]),
        name=row["name"],
        operator=row["operator"],
        profile=row["profile"],
        status=row["status"],
        aurora_version=row["aurora_version"],
        platform=row["platform"],
        config_json=row["config_json"],
        notes=row["notes"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


class AssessmentRepository:
    """CRUD operations for assessments."""

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection

    def create(
        self,
        *,
        name: str,
        operator: str,
        profile: str,
        aurora_version: str,
        platform: str,
        config: AuroraConfig,
        notes: str | None = None,
    ) -> AssessmentRecord:
        cleaned_name = name.strip()
        if not cleaned_name or len(cleaned_name) > 200:
            raise StorageError("assessment name must be 1-200 characters")

        payload: Mapping[str, Any] = config.to_dict()
        created_at = utc_now_iso()

        try:
            cursor = self._connection.execute(
                """
                INSERT INTO assessments
                    (name, operator, profile, aurora_version, platform,
                     config_json, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cleaned_name,
                    operator,
                    profile,
                    aurora_version,
                    platform,
                    json.dumps(payload, sort_keys=True),
                    notes,
                    created_at,
                ),
            )
            self._connection.commit()
        except sqlite3.Error as exc:
            raise StorageError(f"cannot create assessment: {exc}") from exc

        record = self.get(int(cursor.lastrowid))
        if record is None:  # pragma: no cover - insert succeeded above
            raise StorageError("assessment was inserted but could not be read back")
        return record

    def get(self, assessment_id: int) -> AssessmentRecord | None:
        try:
            row = self._connection.execute(
                "SELECT * FROM assessments WHERE id = ?", (int(assessment_id),)
            ).fetchone()
        except sqlite3.Error as exc:
            raise StorageError(f"cannot read assessment {assessment_id}: {exc}") from exc
        return _record(row) if row is not None else None

    def list(self, *, limit: int = 50) -> tuple[AssessmentRecord, ...]:
        if limit < 1:
            raise StorageError("limit must be at least 1")
        try:
            rows = self._connection.execute(
                "SELECT * FROM assessments ORDER BY created_at DESC, id DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"cannot list assessments: {exc}") from exc
        return tuple(_record(row) for row in rows)

    def count(self) -> int:
        try:
            row = self._connection.execute("SELECT COUNT(*) AS total FROM assessments").fetchone()
        except sqlite3.Error as exc:
            raise StorageError(f"cannot count assessments: {exc}") from exc
        return int(row["total"]) if row is not None else 0
