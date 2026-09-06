# SAT-SA — Final Demo Runbook

**Target**: ~2-minute reproducible demonstration.

## Problem

Manual supervisory SOC review of periodic CSE (Cyber Security
Exercise) evidence is expensive and difficult to scale. A single
analyst cannot review thousands of alerts, hundreds of closures,
and the full investigation history for every entity in the
required time.

## Input

Periodic CSE evidence: alert metadata, case-management records,
investigation workflow, escalations, closures, asset inventory.

## Intelligence

Five implemented analytical workers:

* `execution_gap.signal_5_1` — acknowledged alert without
  investigation evidence
* `execution_gap.signal_5_2` — critical/high alert closed
  unusually quickly
* `execution_gap.signal_5_3` — critical alert closed without
  escalation
* `execution_gap.signal_5_4` — shallow investigation
* `execution_gap.signal_5_5` — alert without remediation evidence
* `negative_space.no_activity` — critical asset with no alerts
* `negative_space.low_submission` — low alert-rate submission
* `anomaly.closure_duration` — robust z-score outlier (median / MAD)

The five SIH 26157 intelligence categories are addressed:
execution gaps, negative space, anomalies, peer benchmarking,
entity risk.

## Decision support

* Decomposable entity risk (six components; no single number).
* Priority queue with rationale per alert.
* Peer benchmarks (median critical closure, alert volume, etc.)
  with documented deviation.

## Explainability

* Every finding has a "what / why / evidence / recommendation"
  structure.
* Every observation links to the source record.
* The rationale for every priority is human-readable.

## Trust

* SHA-256 evidence digests.
* Lamport-style one-time signatures (post-quantum-style hash-based
  integrity; air-gap-safe; no external dependencies).
* Merkle root of the audit trail.
* Tamper tests in the test suite: valid, modified evidence,
  modified finding, broken provenance, invalid signature,
  altered chain.

## Human

* Review Queue with priority ordering.
* Human actions: confirm, dismiss, escalate, annotate,
  request_manual_review. Every action is recorded with actor,
  timestamp, target, reason, evidence digest.

## Deployment

* Air-gapped by design. No OpenRouter, no cloud LLMs, no SaaS,
  no remote models, no telemetry. Pure Python standard library.
* QuantumLab 789/789 backend tests still pass (zero regression).

## Demo sequence (~2 minutes)

1. **Open SAT-SA** (sidebar link).
2. **Overview** → click "Load Demo Assessment (CSE-002)".
3. The risk panel shows six components. Note: the
   `execution_gap` component is high; `negative_space` is low
   (CSE-002 has activity, just suspicious activity).
4. **Demo** tab → "Load demo" (CSE-002) → see ground truth
   "execution_gap_present".
5. **Findings** tab → see the per-observation table (5.1, 5.2,
   5.3 all fire).
6. **Review Queue** tab → see the priority list; pick an
   action (e.g. escalate), provide a reason, submit.
7. **Analytics** tab → per-worker observation counts.
8. **Benchmarks** tab → CSE-001 healthy vs CSE-002 pathological
   side-by-side.
9. **Evidence** tab → SHA-256 evidence digest, Lamport signature,
   Merkle audit root.
10. **Reports** tab → download JSON or CSV.
11. **System** tab → deployment audit, registered workers.

## Ground truth (for the demo)

| CSE | Ground truth | What the system finds |
|-----|--------------|------------------------|
| 001 | healthy_baseline | low risk on every component |
| 002 | execution_gap_present | signals 5.1, 5.2, 5.3 fire |
| 003 | negative_space_present | `negative_space.no_activity` fires |
| 004 | anomaly_present | `anomaly.closure_duration` fires (1-min outlier) |
| 005 | peer_deviation_present | median critical closure deviates from peers |

The system is honest: it reports what it actually computed. If a
signal does not fire, the absence is real (the data does not
support it).
