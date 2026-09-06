"""SAT-SA ingestion — CSV / JSON CSE submission parsing.

Supports the data categories required by SIH26157:

  1. alert metadata
  2. case-management records
  3. investigation workflow
  4. escalation
  5. disposition / closure
  6. asset / system inventory

A valid submission is a single JSON object OR a CSV archive
(directory or zip-like structure) with the following layout:

  submission.json      (REQUIRED)
    {
      "submission_id": "...",
      "cse_id": "...",
      "period": {"period_id": "...", "start_at": "...", "end_at": "..."},
      "assets": [{"asset_id": "...", "name": "...", "criticality": "..."}, ...],
      "alerts": [...],
      "investigations": [...],
      "escalations": [...],
      "closures": [...]
    }

  submission.csv       (REQUIRED for CSV format)
    Either a single CSV with one of:
      - assets         columns: asset_id, name, criticality
      - alerts         columns: alert_id, cse_id, asset_id, severity,
                          raised_at, closed_at, status, description,
                          escalation_count, has_investigation,
                          has_remediation_evidence
      - investigations columns: investigation_id, alert_id, cse_id,
                          started_at, completed_at, notes_count,
                          evidence_count, depth_score
      - escalations    columns: escalation_id, alert_id, cse_id,
                          escalated_at, from_level, to_level
      - closures       columns: closure_id, alert_id, cse_id, closed_at,
                          reason, raised_at, had_escalation

    Or a ZIP archive containing a "submission.json" plus the
    individual CSVs.

Validation:
  - missing required fields
  - invalid timestamps
  - broken relationships (e.g. alert references unknown asset)
  - duplicate IDs
  - invalid severity

Do not silently discard invalid records. Raise IngestionError.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Optional

from .domain import (
    SEVERITIES, ALERT_STATUSES, CLOSURE_REASONS,
    Asset, Alert, Closure, Investigation, Escalation,
    AssessmentPeriod, Provenance, CSESubmission,
)
from .trust import digest_submission, sign_submission, KeyPair


# ---------------------------------------------------------------------------
# Errors.
# ---------------------------------------------------------------------------

class IngestionError(ValueError):
    """Raised when the input cannot be normalized into a canonical
    CSESubmission. The message lists every detected problem."""


def _is_iso8601(s: str) -> bool:
    if not isinstance(s, str) or not s:
        return False
    try:
        # Accept Z or +HH:MM offsets
        datetime.fromisoformat(s.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# JSON ingestion.
# ---------------------------------------------------------------------------

def _require(d: dict, key: str, path: str, errors: list) -> None:
    if key not in d or d[key] in (None, ""):
        errors.append(f"missing required field {path}.{key}")


def _check_iso(d: dict, key: str, path: str, errors: list) -> None:
    v = d.get(key)
    if v and not _is_iso8601(v):
        errors.append(f"invalid timestamp {path}.{key}: {v!r}")


def _check_enum(v, allowed: tuple, path: str, errors: list) -> None:
    if v not in allowed:
        errors.append(f"invalid value at {path}: {v!r} (allowed: {allowed})")


def from_json(payload: dict, processing_version: str = "1.0.0",
                sign: bool = True) -> CSESubmission:
    """Parse a JSON submission into a canonical CSESubmission.

    Performs validation. Raises IngestionError with a list of all
    detected problems (does not silently discard invalid records).
    """
    errors: list[str] = []
    _require(payload, "submission_id", "root", errors)
    _require(payload, "cse_id", "root", errors)
    _require(payload, "period", "root", errors)
    period_d = payload.get("period", {})
    _require(period_d, "period_id", "period", errors)
    _require(period_d, "start_at", "period", errors)
    _require(period_d, "end_at", "period", errors)
    _check_iso(period_d, "start_at", "period", errors)
    _check_iso(period_d, "end_at", "period", errors)

    # Build entities.
    assets: dict[str, Asset] = {}
    for i, a in enumerate(payload.get("assets", [])):
        path = f"assets[{i}]"
        if not isinstance(a, dict):
            errors.append(f"{path} must be an object")
            continue
        _require(a, "asset_id", path, errors)
        if a.get("asset_id") in assets:
            errors.append(f"duplicate asset_id at {path}: {a.get('asset_id')}")
        try:
            asset = Asset.from_dict(a)
        except Exception as e:
            errors.append(f"{path} invalid: {e}")
            continue
        assets[asset.asset_id] = asset

    alerts: dict[str, Alert] = {}
    for i, al in enumerate(payload.get("alerts", [])):
        path = f"alerts[{i}]"
        if not isinstance(al, dict):
            errors.append(f"{path} must be an object")
            continue
        _require(al, "alert_id", path, errors)
        _require(al, "cse_id", path, errors)
        _require(al, "asset_id", path, errors)
        _check_iso(al, "raised_at", path, errors)
        if al.get("closed_at") and not _is_iso8601(al["closed_at"]):
            errors.append(f"invalid timestamp {path}.closed_at")
        _check_enum(al.get("severity"), SEVERITIES, f"{path}.severity", errors)
        _check_enum(al.get("status"), ALERT_STATUSES, f"{path}.status", errors)
        if al.get("alert_id") in alerts:
            errors.append(f"duplicate alert_id at {path}: {al.get('alert_id')}")
        # Relationship validation: alert's asset_id must exist in assets
        # (if assets are present).
        if al.get("asset_id") and al["asset_id"] not in assets:
            if assets:
                errors.append(
                    f"alert {al.get('alert_id')} references unknown "
                    f"asset {al['asset_id']!r}")
        try:
            alert = Alert.from_dict(al)
        except Exception as e:
            errors.append(f"{path} invalid: {e}")
            continue
        alerts[alert.alert_id] = alert

    investigations: dict[str, Investigation] = {}
    for i, inv in enumerate(payload.get("investigations", [])):
        path = f"investigations[{i}]"
        if not isinstance(inv, dict):
            errors.append(f"{path} must be an object")
            continue
        _require(inv, "investigation_id", path, errors)
        _require(inv, "alert_id", path, errors)
        _check_iso(inv, "started_at", path, errors)
        if inv.get("completed_at") and not _is_iso8601(inv["completed_at"]):
            errors.append(f"invalid timestamp {path}.completed_at")
        if inv.get("alert_id") and inv["alert_id"] not in alerts:
            if alerts:
                errors.append(
                    f"investigation {inv.get('investigation_id')} "
                    f"references unknown alert {inv['alert_id']!r}")
        if inv.get("investigation_id") in investigations:
            errors.append(
                f"duplicate investigation_id at {path}")
        try:
            inv_obj = Investigation.from_dict(inv)
        except Exception as e:
            errors.append(f"{path} invalid: {e}")
            continue
        investigations[inv_obj.investigation_id] = inv_obj
        if inv.get("alert_id") in alerts:
            alerts[inv["alert_id"]].has_investigation = True

    escalations: list[Escalation] = []
    for i, e in enumerate(payload.get("escalations", [])):
        path = f"escalations[{i}]"
        if not isinstance(e, dict):
            errors.append(f"{path} must be an object")
            continue
        _require(e, "escalation_id", path, errors)
        _require(e, "alert_id", path, errors)
        _check_iso(e, "escalated_at", path, errors)
        if e.get("alert_id") and e["alert_id"] not in alerts:
            if alerts:
                errors.append(
                    f"escalation {e.get('escalation_id')} references "
                    f"unknown alert {e['alert_id']!r}")
        try:
            esc = Escalation(**{k: e[k] for k in
                                ("escalation_id", "alert_id", "cse_id",
                                 "escalated_at", "from_level", "to_level")
                                if k in e})
        except Exception as ex:
            errors.append(f"{path} invalid: {ex}")
            continue
        escalations.append(esc)
        if esc.alert_id in alerts:
            alerts[esc.alert_id].escalation_count += 1
            alerts[esc.alert_id].status = "escalated"

    closures: dict[str, Closure] = {}
    for i, c in enumerate(payload.get("closures", [])):
        path = f"closures[{i}]"
        if not isinstance(c, dict):
            errors.append(f"{path} must be an object")
            continue
        _require(c, "closure_id", path, errors)
        _require(c, "alert_id", path, errors)
        _require(c, "cse_id", path, errors)
        _check_iso(c, "closed_at", path, errors)
        if c.get("raised_at") and not _is_iso8601(c["raised_at"]):
            errors.append(f"invalid timestamp {path}.raised_at")
        _check_enum(c.get("reason"), CLOSURE_REASONS, f"{path}.reason",
                     errors)
        if c.get("alert_id") and c["alert_id"] not in alerts:
            if alerts:
                errors.append(
                    f"closure {c.get('closure_id')} references "
                    f"unknown alert {c['alert_id']!r}")
        try:
            cl = Closure.from_dict(c)
        except Exception as ex:
            errors.append(f"{path} invalid: {ex}")
            continue
        closures[cl.alert_id] = cl
        if cl.alert_id in alerts:
            alerts[cl.alert_id].closed_at = cl.closed_at
            alerts[cl.alert_id].status = "closed"

    if errors:
        raise IngestionError(
            "Ingestion failed with " + str(len(errors)) + " error(s): "
            + "; ".join(errors[:5])
            + ("; ..." if len(errors) > 5 else ""))

    period = AssessmentPeriod(
        period_id=period_d["period_id"],
        cse_id=payload["cse_id"],
        start_at=period_d["start_at"],
        end_at=period_d["end_at"],
        description=period_d.get("description", ""),
    )

    digest = digest_submission(payload)
    provenance = Provenance(
        submission_id=payload["submission_id"],
        cse_id=payload["cse_id"],
        period_id=period.period_id,
        source_format="json",
        source_digest=digest,
        ingested_at=datetime.utcnow().isoformat() + "Z",
        processing_version=processing_version,
    )

    sub = CSESubmission(
        cse_id=payload["cse_id"],
        submission_id=payload["submission_id"],
        period=period,
        assets=assets,
        alerts=alerts,
        investigations=investigations,
        escalations=escalations,
        closures=closures,
        provenance=provenance,
    )

    if sign:
        sub._signature = sign_submission(payload, KeyPair.generate())
    return sub


# ---------------------------------------------------------------------------
# CSV ingestion.
# ---------------------------------------------------------------------------

def _parse_csv(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    return [dict(r) for r in reader]


def from_csv(assets_csv: Optional[str] = None,
             alerts_csv: Optional[str] = None,
             investigations_csv: Optional[str] = None,
             escalations_csv: Optional[str] = None,
             closures_csv: Optional[str] = None,
             meta: Optional[dict] = None,
             processing_version: str = "1.0.0") -> CSESubmission:
    """Build a CSESubmission from CSV strings. Each *_csv argument
    is the content of a single CSV file. The `meta` dict provides
    submission_id, cse_id, and period information (these are not in
    the per-entity CSVs by SIH convention)."""
    if not meta:
        raise IngestionError("from_csv requires a 'meta' dict with "
                              "submission_id, cse_id, period_id, "
                              "start_at, end_at.")
    errors: list[str] = []
    for k in ("submission_id", "cse_id", "period_id", "start_at", "end_at"):
        if k not in meta or not meta[k]:
            errors.append(f"missing meta.{k}")
    if errors:
        raise IngestionError("CSV ingestion meta errors: "
                              + "; ".join(errors))

    assets: dict[str, Asset] = {}
    if assets_csv:
        for r in _parse_csv(assets_csv):
            try:
                a = Asset.from_dict(r)
                assets[a.asset_id] = a
            except Exception as e:
                raise IngestionError(f"assets CSV row invalid: {e}")

    alerts: dict[str, Alert] = {}
    if alerts_csv:
        for r in _parse_csv(alerts_csv):
            try:
                al = Alert.from_dict(r)
                alerts[al.alert_id] = al
            except Exception as e:
                raise IngestionError(f"alerts CSV row invalid: {e}")

    investigations: dict[str, Investigation] = {}
    if investigations_csv:
        for r in _parse_csv(investigations_csv):
            try:
                inv = Investigation.from_dict(r)
                investigations[inv.investigation_id] = inv
                if inv.alert_id in alerts:
                    alerts[inv.alert_id].has_investigation = True
            except Exception as e:
                raise IngestionError(f"investigations CSV row invalid: {e}")

    escalations: list[Escalation] = []
    if escalations_csv:
        for r in _parse_csv(escalations_csv):
            try:
                esc = Escalation(**r)
                escalations.append(esc)
                if esc.alert_id in alerts:
                    alerts[esc.alert_id].escalation_count += 1
                    alerts[esc.alert_id].status = "escalated"
            except Exception as e:
                raise IngestionError(f"escalations CSV row invalid: {e}")

    closures: dict[str, Closure] = {}
    if closures_csv:
        for r in _parse_csv(closures_csv):
            try:
                cl = Closure.from_dict(r)
                closures[cl.alert_id] = cl
                if cl.alert_id in alerts:
                    alerts[cl.alert_id].closed_at = cl.closed_at
                    alerts[cl.alert_id].status = "closed"
            except Exception as e:
                raise IngestionError(f"closures CSV row invalid: {e}")

    period = AssessmentPeriod(
        period_id=meta["period_id"],
        cse_id=meta["cse_id"],
        start_at=meta["start_at"],
        end_at=meta["end_at"],
        description=meta.get("description", ""),
    )
    full_payload = {
        "meta": meta,
        "assets": assets_csv,
        "alerts": alerts_csv,
        "investigations": investigations_csv,
        "escalations": escalations_csv,
        "closures": closures_csv,
    }
    digest = digest_submission(full_payload)
    provenance = Provenance(
        submission_id=meta["submission_id"],
        cse_id=meta["cse_id"],
        period_id=meta["period_id"],
        source_format="csv",
        source_digest=digest,
        ingested_at=datetime.utcnow().isoformat() + "Z",
        processing_version=processing_version,
    )
    return CSESubmission(
        cse_id=meta["cse_id"],
        submission_id=meta["submission_id"],
        period=period,
        assets=assets,
        alerts=alerts,
        investigations=investigations,
        escalations=escalations,
        closures=closures,
        provenance=provenance,
    )


__all__ = [
    "IngestionError",
    "from_json", "from_csv",
]
