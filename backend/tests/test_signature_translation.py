"""Temporal fault signatures must preserve injection transients."""
from app.qec.rotated_surface_code import RotatedSurfaceCode
from app.qec.circuit_level import simulate_circuit_level
from app.qec.circuit_signatures import build_signature_db
from app.qec.correlation_decoder import _remove_contribution


def test_delayed_readout_signature_clears_observed_transient():
    code = RotatedSurfaceCode.build(3)
    mode = "baseline_h_cnot_h"
    fault = ("X", 0, "readout", 0, None, None)
    # Two-round production history after injection. Prefix an ideal round:
    # a readout fault changes no data, so this is the same physical history
    # with injection delayed until round two of three.
    _, _, _, injected, _, _ = simulate_circuit_level(
        code, 2, 0.0, 0.0, 0.0, 0.0, seed=0,
        extraction_model=mode, forced_faults=[fault])
    ideal = (tuple(0 for _ in code.x_checks),
             tuple(0 for _ in code.z_checks))
    observed = [ideal, *injected]
    db = build_signature_db(code, 3, mode)
    original = next(s for s in db.mid
                    if s.contrib[0] == tuple(tuple(bits) for bits in injected[0])
                    and not s.data_x and not s.data_z)
    signature = next(s for s, t in db.translated_mid()
                     if t == 2 and s.example == original.example)
    residual = _remove_contribution(observed, signature, 2)
    assert all(not any(x) and not any(z) for x, z in residual)


def test_delayed_m19_fault_recovers_at_absolute_event_layer():
    from app.qec.correlation_decoder import decode_correlation_aware
    code = RotatedSurfaceCode.build(5)
    mode = "baseline_h_cnot_h"
    fault = ("X", 3, "cnot", 0, "t", "Y")
    ex, ez, _, injected, _, _ = simulate_circuit_level(
        code, 2, 0.0, 0.0, 0.0, 0.0, seed=0,
        extraction_model=mode, forced_faults=[fault])
    ideal = (tuple(0 for _ in code.x_checks),
             tuple(0 for _ in code.z_checks))
    result = decode_correlation_aware(
        code, 3, 0.0, 0.0, 0.0, 0.0,
        observed_syndromes=[ideal, *injected],
        data_error_x=ex, data_error_z=ez,
        db=build_signature_db(code, 3, mode), seed=0)
    assert result.success
    assert result.attributed_round == 2
