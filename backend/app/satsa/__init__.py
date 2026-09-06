"""SAT-SA (Supervisory Analytics Tool for SOC Assessment) — SIH 26157.

A new top-level subsystem alongside QuantumLab. Reuses QuantumLab's
persistence and experiment infrastructure where appropriate.

Modules:
  domain             canonical entities (CSE, Alert, Case, Asset, ...)
  ingestion          CSV/JSON parsers, validation, normalization
  trust              cryptographic provenance + integrity (PQC)
  analysis_run       AnalysisRun orchestration
  workers            analytical workers (execution gap, negative space, anomaly)
  risk               entity risk
  review             human review
  benchmark          peer comparison
  registry           worker/analyser registration
"""
