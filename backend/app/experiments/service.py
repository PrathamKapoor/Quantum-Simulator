"""Experiment service: persistence-backed experiment/run lifecycle.

States (directive §98): CREATED QUEUED RUNNING PAUSED CANCELLING CANCELLED
COMPLETED FAILED PARTIAL. A partial run is never reported as completed (§329).
"""
from __future__ import annotations

from ..persistence.db import Database, ensure_default_project, _utcnow
from ..workers.process_worker import WorkerSpec
from .runner import ExperimentSpec, execute_run, expand_sweep, RESULT_SCHEMA, RESULT_VERSION


class CancelledRunError(RuntimeError):
    """Raised when an isolated execution was cancelled (§29)."""


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

    def load_run_spec(self, run_id: int) -> WorkerSpec:
        """Serializable experiment specification for a worker process (§11).

        Raises ValueError for unknown runs and for runs already RUNNING, so
        the caller can fail honestly before spawning anything."""
        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Unknown run {run_id}.")
        if run["status"] in ("RUNNING", "CANCELLING"):
            raise ValueError(f"Run {run_id} is already running.")
        module_row = self.db.query_one(
            "SELECT module FROM experiments WHERE id = ?", (run["experiment_id"],))
        if not module_row:
            raise ValueError(f"Run {run_id} has no experiment row.")
        return WorkerSpec(
            run_id=run_id,
            module=module_row["module"],
            resolved_config=self.db.loads(run["resolved_config"]),
            seed=int(run["seed"] or 0),
        )

    def begin_run(self, run_id: int) -> None:
        self.db.execute(
            "UPDATE runs SET status='RUNNING', started_at=?, progress=0 WHERE id=?",
            (_utcnow(), run_id))

    def update_run_progress(self, run_id: int, frac: float, detail: str) -> None:
        self.db.execute(
            "UPDATE runs SET progress = ?, progress_detail = ? WHERE id = ?",
            (float(frac), str(detail), run_id),
        )

    def persist_run_success(self, run_id: int, doc: dict) -> int:
        cur = self.db.execute(
            "INSERT INTO results (run_id, schema_name, schema_version, payload, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (run_id, RESULT_SCHEMA, RESULT_VERSION, self.db.dumps(doc), _utcnow()),
        )
        result_id = int(cur.lastrowid)
        self.db.execute(
            "UPDATE runs SET status='COMPLETED', completed_at=?, result_id=?, metrics=? "
            "WHERE id=?",
            (_utcnow(), result_id, self.db.dumps(doc.get("metrics", {})), run_id))
        self.db.audit("run", run_id, "completed")
        return result_id

    def persist_run_failure(self, run_id: int, code: str, message: str) -> None:
        self.db.execute(
            "UPDATE runs SET status='FAILED', completed_at=?, "
            "error_code=?, error_message=? WHERE id=?",
            (_utcnow(), code, str(message)[:2000], run_id))
        self.db.audit("run", run_id, "failed", f"{code}: {message}")

    def mark_run_cancelled(self, run_id: int) -> None:
        self.db.execute(
            "UPDATE runs SET status='CANCELLED', completed_at=? WHERE id=?",
            (_utcnow(), run_id))
        self.db.audit("run", run_id, "cancelled")

    def execute_run_now(self, run_id: int, progress_callback=None) -> dict:
        """Synchronously execute a stored run IN THIS PROCESS.

        Kept as the documented in-process path for direct service use (tests,
        scripts). The API job queue and reproduction use
        :meth:`execute_run_isolated`, which runs the computation in a worker
        process (AD-014)."""
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
            self.update_run_progress(run_id, frac, detail)
            if progress_callback:
                progress_callback(float(frac), str(detail))

        self.begin_run(run_id)
        try:
            doc = execute_run(module, resolved, seed, cb)
        except Exception as exc:
            code = type(exc).__name__
            self.persist_run_failure(run_id, code, str(exc))
            raise
        self.persist_run_success(run_id, doc)
        return doc

    def execute_run_isolated(self, run_id: int, *, timeout_s: float | None = None,
                             progress_callback=None) -> dict:
        """Execute a stored run in a fresh worker process (AD-014).

        The parent owns persistence; the worker only computes and reports.
        Raises on failure like execute_run_now (after recording FAILED)."""
        spec = self.load_run_spec(run_id)
        self.begin_run(run_id)
        from ..workers.process_worker import run_spec_in_process

        def _on_progress(frac, detail):
            self.update_run_progress(run_id, frac, detail)
            if progress_callback:
                progress_callback(frac, detail)

        result = run_spec_in_process(
            spec, on_progress=_on_progress, timeout_s=timeout_s)
        if result.ok and isinstance(result.result, dict):
            self.persist_run_success(run_id, result.result)
            return result.result
        if result.cancelled:
            self.mark_run_cancelled(run_id)
            raise CancelledRunError(f"Run {run_id} cancelled during execution.")
        code = result.error_type or "WorkerError"
        message = result.error_message or "worker failed without a result"
        self.persist_run_failure(run_id, code, message)
        raise RuntimeError(f"{code}: {message}")

    def recover_interrupted_runs(self) -> dict:
        """Startup recovery for runs orphaned by a previous process exit.

        Policy (AD-014, documented): RUNNING/CANCELLING runs can no longer
        have a live worker (the queue is in-process and volatile), so they
        become FAILED with error_code INTERRUPTED_BY_RESTART - never silently
        COMPLETED. QUEUED runs return to CREATED so they can be re-executed
        (the in-memory queue does not survive restarts)."""
        recovered = {"failed": 0, "unqueued": 0}
        rows = self.db.query(
            "SELECT id FROM runs WHERE status IN ('RUNNING', 'CANCELLING')")
        for row in rows:
            self.persist_run_failure(row["id"], "INTERRUPTED_BY_RESTART",
                                     "process exited while the run was running.")
            recovered["failed"] += 1
        rows = self.db.query("SELECT id FROM runs WHERE status = 'QUEUED'")
        for row in rows:
            self.db.execute(
                "UPDATE runs SET status='CREATED' WHERE id=?", (row["id"],))
            recovered["unqueued"] += 1
        return recovered

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

    # ---------------- reproducibility ----------------

    def reproduce_run(self, run_id: int) -> "ReproductionReport":
        """Re-execute the stored configuration+seed as a NEW run and compare
        result documents (directive §44). The original run is never modified
        (§127 immutability of completed runs)."""
        from .reproducibility import ReproductionReport, compare_result_documents

        original = self.get_run(run_id)
        if not original:
            raise ValueError(f"Unknown run {run_id}.")
        if original["status"] != "COMPLETED":
            raise ValueError(
                f"Run {run_id} is {original['status']}; only COMPLETED runs "
                "can be reproduced."
            )
        cur = self.db.execute(
            "INSERT INTO runs (experiment_id, run_index, label, resolved_config, "
            "backend, noise_model, seed, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'CREATED', ?)",
            (original["experiment_id"], original["run_index"],
             f"reproduce-of-{run_id}", original["resolved_config"],
             original["backend"], original["noise_model"], original["seed"],
             _utcnow()))
        new_run_id = int(cur.lastrowid)
        self.execute_run_isolated(new_run_id)
        original_doc = self.get_result(run_id)
        reproduced_doc = self.get_result(new_run_id)
        if not original_doc or not reproduced_doc:
            report = ReproductionReport(
                run_id=run_id, reproduced_run_id=new_run_id,
                status="ERROR", differences=["missing stored result document"])
            report.reproduced_run_id = new_run_id
            return report
        report = compare_result_documents(
            original_doc["document"], reproduced_doc["document"])
        report.run_id = run_id
        report.reproduced_run_id = new_run_id
        self.db.audit("run", run_id, "reproduced",
                      f"{report.status} via run {new_run_id}")
        return report

    def export_run_csv(self, run_id: int) -> str:
        """Provenance-rich CSV export of an artifacts table (§97).

        Every row carries experiment/run ids and seed so exported data can be
        traced back to its provenance.
        """
        import csv
        import io

        run = self.get_run(run_id)
        if not run:
            raise ValueError(f"Unknown run {run_id}.")
        res = self.get_result(run_id)
        if not res:
            raise ValueError(f"Run {run_id} has no stored result.")
        doc = res["document"]
        table = (doc.get("artifacts") or {}).get("table")             or [doc.get("metrics", {})]
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["experiment_id", "run_id", "seed", *table[0].keys()])
        for row in table:
            writer.writerow([run["experiment_id"], run_id, run["seed"],
                             *row.values()])
        return buf.getvalue()

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
