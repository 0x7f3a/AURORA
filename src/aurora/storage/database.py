"""SQLite connection management and migration application.

Each :class:`Database` owns one connection. Connections are not shared across
threads (``sqlite3``'s default ``check_same_thread`` guard is left enabled)
because sharing them is a common source of subtle corruption and deadlocks.
Concurrent access from the asynchronous engine will use one connection per
worker, added when the async engine exists.

``initialize`` is idempotent and forward-only; a database written by a newer
AURORA is refused rather than silently downgraded.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from aurora.errors import StorageError
from aurora.storage.schema import MIGRATIONS, SCHEMA_VERSION

__all__ = ["Database"]


class Database:
    """A single-connection SQLite database."""

    def __init__(self, path: Path | str, *, busy_timeout_ms: int = 5000) -> None:
        self._path = Path(path)
        self._busy_timeout_ms = int(busy_timeout_ms)
        self._connection: sqlite3.Connection | None = None

    @classmethod
    def in_memory(cls) -> "Database":
        """An ephemeral database, used by tests and dry runs."""

        return cls(":memory:")

    @property
    def path(self) -> Path:
        return self._path

    @property
    def is_memory(self) -> bool:
        return str(self._path) == ":memory:"

    def connect(self) -> sqlite3.Connection:
        """Open the connection on first use and apply connection pragmas."""

        if self._connection is not None:
            return self._connection

        if not self.is_memory:
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise StorageError(f"cannot create database directory {self._path.parent}: {exc}") from exc

        try:
            connection = sqlite3.connect(
                str(self._path),
                timeout=self._busy_timeout_ms / 1000,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute(f"PRAGMA busy_timeout = {self._busy_timeout_ms}")
            if not self.is_memory:
                # WAL improves concurrent readers. It is unavailable on some
                # filesystems (network shares, for example); falling back to the
                # default journal is acceptable and is not hidden from the user.
                try:
                    connection.execute("PRAGMA journal_mode = WAL")
                except sqlite3.OperationalError:
                    pass
        except sqlite3.Error as exc:
            raise StorageError(f"cannot open database {self._path}: {exc}") from exc

        self._connection = connection
        return connection

    def initialize(self) -> int:
        """Create or migrate the schema and return the resulting version."""

        connection = self.connect()
        current = _read_user_version(connection)
        if current > SCHEMA_VERSION:
            raise StorageError(
                f"database schema version {current} is newer than this build supports "
                f"({SCHEMA_VERSION})",
                hint="upgrade AURORA or point --home at another workspace",
            )

        try:
            for migration in MIGRATIONS:
                if migration.version <= current:
                    continue
                for statement in migration.statements:
                    connection.execute(statement)
                connection.execute(f"PRAGMA user_version = {int(migration.version)}")
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise StorageError(f"schema initialization failed for {self._path}: {exc}") from exc

        return self.schema_version()

    def schema_version(self) -> int:
        """The schema version recorded in the database (0 when uninitialised)."""

        return _read_user_version(self.connect())

    def require_initialized(self) -> int:
        """Raise unless the database carries the current schema."""

        version = self.schema_version()
        if version == 0:
            raise StorageError(
                f"database is not initialized: {self._path}",
                hint="run 'aurora init' to create the workspace",
            )
        if version < SCHEMA_VERSION:
            raise StorageError(
                f"database schema version {version} is outdated (expected {SCHEMA_VERSION})",
                hint="run 'aurora init' to apply migrations",
            )
        return version

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Run a block in a transaction, committing on success."""

        connection = self.connect()
        try:
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()

    def close(self) -> None:
        if self._connection is None:
            return
        try:
            self._connection.close()
        finally:
            self._connection = None

    def __enter__(self) -> "Database":
        self.require_initialized()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:  # noqa: ANN001 - context protocol
        if self._connection is None:
            return
        try:
            if exc_type is None:
                self._connection.commit()
        finally:
            self.close()


def _read_user_version(connection: sqlite3.Connection) -> int:
    row = connection.execute("PRAGMA user_version").fetchone()
    if row is None:  # pragma: no cover - PRAGMA always returns a row
        return 0
    return int(row[0])
