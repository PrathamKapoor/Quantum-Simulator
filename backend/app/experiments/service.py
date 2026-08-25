"""Experiment service: persistence-backed experiment/run lifecycle.

States (directive §98): CREATED QUEUED RUNNING PAUSED CANCELLING CANCELLED
COMPLETED FAILED PARTIAL. A partial run is never reported as completed (§329).
"""
from __future__ import annotations

from ..persistence.db import Database, ensure_default_project, _utcnow
from .runner import ExperimentSpec, execute_run, expand_sweep, RESULT_SCHEMA, RESULT_VERSION


class ExperimentService:
    """Facade over the database for creating/running/inspecting experiments."""

    def __init__(self, db: Database):
        self.db = db
        self.default_project_id = ensure_default_project(db)

    # ---------------- experiments ----------------

    def create_experiment(self, spec: ExperimentSpec, *, project_id: int | None = None,
                          objective: str = "", hypothesis: str = "",
                          description: str = "") -> int:
        issues = spec.validate()
        if issues:
            raise ValueError("Invalid experiment: " + "; ".join(issues))
        pid = project_id or self.default_project_id
        cur = self.db.execute(
            "INSERT INTO experiments (project_id, name, module, description, "
            "objective, hypothesis, base_config, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, spec.name.strip(), spec.module, description,
             objective, hypothesis, self.db.dumps(spec.to_dict()),
             _utcnow(), _utcnow()),
        )
        exp_id = int(cur.lastrowid)
        self.db.audit("experiment", exp_id, "created", spec.name)
        return exp_id

    def get_experiment(self, experiment_id: int):
        row = self.db.query_one("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
        return dict(row) if row else None

    def list_experiments(self, limit: int = 100):
        rows = self.db.query(
            "SELECT e.*, COUNT(r.id) AS run_count FROM experiments e "
            "LEFT JOIN runs r ON r.experiment_id = e.id "
            "GROUP BY e.id ORDER BY e.id DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # ---------------- runs ----------------

    def create_runs_for_experiment(self, experiment_id: int) -> list[int]:
        """Materialize one run per sweep combination (status CREATED)."""
        exp = self.get_experiment(experiment_id)
        if not exp:
            raise ValueError(f"Unknown experiment {experiment_id}.")
        spec = ExperimentSpec.from_dict(self.db.loads(exp["base_config"]))
        combos = expand_sweep(spec)
        run_ids = []
        for i, (label, resolved) in enumerate(combos):
            cur = self.db.execute(
                "INSERT INTO runs (experiment_id, run_index, label, resolved_config, "
                "backend, noise_model, seed, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'CREATED', ?)",
                (experiment_id, i, label, self.db.dumps(resolved),
                 spec.backend, spec.noise_model or "ideal", spec.seed + 7919 * i,
                 _utcnow()),
            )
            run_ids.append(int(cur.lastrowid))
        self.db.audit("experiment", experiment_id, "runs_created",
                      f"{len(run_ids)} run(s)")
        return run_ids

    def get_run(self, run_id: int):
        row = self.db.query_one("SELECT * FROM runs WHERE id = ?", (run_id,))
        return dict(row) if row else None

    def list_runs(self, experiment_id: int):
        rows = self.db.query(
            "SELECT * FROM runs WHERE experiment_id = ? ORDER BY run_index",
            (experiment_id,))
        return [dict(r) for r in rows]

    # ---------------- execution ----------------

    def execute_run_now(self, run_id: int, progress_callback=None) -> dict:
        """Synchronously execute a stored run. Used directly by tests and by
        the worker; the API layer schedules it on a worker thread."""
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Unknown run {run_id}.")
        if run["status"] in ("RUNNING",):
            raise ValueError(f"Run {run_id} is already running.")
        resolved = self.db.loads(run["resolved_config"])
        module_row = self.db.query_one(
            "SELECT module FROM experiments WHERE id = ?", (run["experiment_id"],))
        module = module_row["module"]
        seed = int(run["seed"] or 0)

        def cb(frac, detail):
            self.db.execute(
                "UPDATE runs SET progress = ?, progress_detail = ? WHERE id = ?",
                (float(frac), str(detail), run_id),
            )
            if progress_callback:
                progress_callback(float(frac), str(detail))

        self.db.execute(
            "UPDATE runs SET status='RUNNING', started_at=?, progress=0 WHERE id=?",
            (_utcnow(), run_id))
        try:
            doc = execute_run(module, resolved, seed, cb)
        except Exception as exc:
            code = type(exc).__name__
            self.db.execute(
                "UPDATE runs SET status='FAILED', completed_at=?, "
                "error_code=?, error_message=? WHERE id=?",
                (_utcnow(), code, str(exc)[:2000], run_id))
            self.db.audit("run", run_id, "failed", f"{code}: {exc}")
            raise
        cur = self.db.execute(
            "INSERT INTO results (run_id, schema_name, schema_version, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, RESULT_SCHEMA, RESULT_VERSION, self.db.dumps(doc), _utcnow()),
        )
        result_id = int(cur.lastrowid)
        self.db.execute(
            "UPDATE runs SET status='COMPLETED', completed_at=?, result_id=?, metrics=? "
            "WHERE id=?",
            (_utcnow(), result_id, self.db.dumps(doc["metrics"]), run_id))
        self.db.audit("run", run_id, "completed")
        return doc

    def cancel_run(self, run_id: int) -> bool:
        run = self.get_run(run_id)
        if not run:
            return False
        if run["status"] in ("CREATED", "QUEUED"):
            self.db.execute(
                "UPDATE runs SET status='CANCELLED', completed_at=? WHERE id=?",
                (_utcnow(), run_id))
            self.db.audit("run", run_id, "cancelled")
            return True
        if run["status"] == "RUNNING":
            self.db.execute(
                "UPDATE runs SET status='CANCELLING' WHERE id=?", (run_id,))
            self.db.audit("run", run_id, "cancel_requested")
            return True
        return False

    # ---------------- results ----------------

    def get_result(self, run_id: int):
        row = self.db.query_one(
            "SELECT * FROM results WHERE run_id = ? ORDER BY id DESC LIMIT 1",
            (run_id,))
        if not row:
            return None
        doc = self.db.loads(row["payload"])
        return {
            "result_id": int(row["id"]),
            "schema": row["schema_name"],
            "version": int(row["schema_version"]),
            "document": doc,
        }

    def compare_runs(self, run_ids: list[int]) -> dict:
        """Comparison across runs of possibly different configs (§107)."""
        rows = []
        for rid in run_ids:
            run = self.get_run(rid)
            if not run:
                continue
            res = self.get_result(rid)
            rows.append({
                "run_id": rid,
                "label": run["label"],
                "status": run["status"],
                "seed": run["seed"],
                "resolved_config": self.db.loads(run["resolved_config"]),
                "metrics": res["document"]["metrics"] if res else None,
            })
        differing_keys = set()
        if len(rows) >= 2:
            base = rows[0]["resolved_config"]
            for other in rows[1:]:
                for k in set(base) | set(other["resolved_config"]):
                    if base.get(k) != other["resolved_config"].get(k):
                        differing_keys.add(k)
        return {"runs": rows, "differing_parameters": sorted(differing_keys)}
