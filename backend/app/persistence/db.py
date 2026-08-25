"""SQLite persistence with explicit, versioned migrations (directive §120-122).

Schema changes only through numbered migration functions recorded in
``schema_migrations``. All scientific objects carry schema names and versions;
stored JSON is validated on load where practical.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH_DEFAULT = "quantumlab.db"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------

MIGRATIONS: list[tuple[int, str, callable]] = []


def migration(number: int, description: str):
    def deco(fn):
        MIGRATIONS.append((number, description, fn))
        return fn
    return deco


@migration(1, "core tables: projects, experiments, runs, results, notes, audit_log")
def _m1(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL REFERENCES projects(id),
            name TEXT NOT NULL,
            module TEXT NOT NULL,
            description TEXT DEFAULT '',
            objective TEXT DEFAULT '',
            hypothesis TEXT DEFAULT '',
            config_version INTEGER NOT NULL DEFAULT 1,
            base_config TEXT NOT NULL,          -- JSON experiment definition
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER NOT NULL REFERENCES experiments(id),
            run_index INTEGER NOT NULL DEFAULT 0,
            label TEXT DEFAULT '',
            resolved_config TEXT NOT NULL,      -- JSON incl. swept parameters
            backend TEXT DEFAULT 'statevector',
            noise_model TEXT DEFAULT 'ideal',
            seed INTEGER,
            status TEXT NOT NULL DEFAULT 'CREATED',
            progress REAL NOT NULL DEFAULT 0.0,
            progress_detail TEXT DEFAULT '',
            metrics TEXT,                       -- JSON summary metrics
            result_id INTEGER,
            error_code TEXT,
            error_message TEXT,
            code_version TEXT DEFAULT '0.1.0',
            created_at TEXT NOT NULL,
            started_at TEXT,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL REFERENCES runs(id),
            schema_name TEXT NOT NULL,
            schema_version INTEGER NOT NULL,
            payload TEXT NOT NULL,              -- JSON result document
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            experiment_id INTEGER REFERENCES experiments(id),
            author TEXT DEFAULT 'user',
            body TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity TEXT NOT NULL,
            entity_id INTEGER,
            action TEXT NOT NULL,
            detail TEXT DEFAULT '',
            at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_runs_experiment ON runs(experiment_id);
        CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
        """
    )


@migration(2, "saved objects: circuits and networks")
def _m2(conn: sqlite3.Connection):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS saved_circuits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id),
            name TEXT NOT NULL,
            schema_name TEXT NOT NULL DEFAULT 'quantumlab.circuit',
            schema_version INTEGER NOT NULL DEFAULT 1,
            document TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS saved_networks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id),
            name TEXT NOT NULL,
            schema_name TEXT NOT NULL DEFAULT 'quantumlab.network',
            schema_version INTEGER NOT NULL DEFAULT 1,
            document TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )


class Database:
    """Threadsafe SQLite wrapper with migration tracking."""

    def __init__(self, path: str = DB_PATH_DEFAULT):
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self.migrate()

    def migrate(self) -> list[int]:
        applied = []
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "number INTEGER PRIMARY KEY, description TEXT, applied_at TEXT)"
            )
            done = {r["number"] for r in self._conn.execute(
                "SELECT number FROM schema_migrations")}
            for number, description, fn in sorted(MIGRATIONS):
                if number in done:
                    continue
                fn(self._conn)
                self._conn.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?, ?)",
                    (number, description, _utcnow()),
                )
                applied.append(number)
            self._conn.commit()
        return applied

    @contextmanager
    def tx(self):
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def execute(self, sql: str, params=()) -> sqlite3.Cursor:
        with self.tx() as conn:
            return conn.execute(sql, params)

    def query(self, sql: str, params=()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params))

    def query_one(self, sql: str, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def close(self):
        with self._lock:
            self._conn.close()

    # -- convenience audit -------------------------------------------------

    def audit(self, entity: str, entity_id: int | None, action: str, detail: str = "") -> None:
        self.execute(
            "INSERT INTO audit_log (entity, entity_id, action, detail, at) "
            "VALUES (?, ?, ?, ?, ?)",
            (entity, entity_id, action, detail, _utcnow()),
        )

    @staticmethod
    def dumps(obj) -> str:
        return json.dumps(obj, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def loads(text: str):
        return json.loads(text)


def ensure_default_project(db: Database) -> int:
    row = db.query_one("SELECT id FROM projects WHERE name = ?", ("default",))
    if row:
        return int(row["id"])
    db.execute(
        "INSERT INTO projects (name, description, created_at, updated_at) "
        "VALUES (?, ?, ?, ?)",
        ("default", "Default research workspace", _utcnow(), _utcnow()),
    )
    row = db.query_one("SELECT id FROM projects WHERE name = ?", ("default",))
    db.audit("project", int(row["id"]), "created", "default project")
    return int(row["id"])
