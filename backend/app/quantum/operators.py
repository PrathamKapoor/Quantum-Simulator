"""Operators and the standard gate library.

Scientific notes
----------------
Gates are represented as dense complex matrices acting on their listed qubit
operands. A matrix is accepted as a gate only if it is unitary within
tolerance: ``U† U ≈ I`` (directive §21). Parameterized rotation gates use
radians. Conventions:

- ``Rx(θ) = exp(-i θ X / 2)``, likewise Ry, Rz.
- ``U3(θ, φ, λ)`` is the standard single-qubit parameterization
  ``[[cos(θ/2), -e^{iλ} sin(θ/2)], [e^{iφ} sin(θ/2), e^{i(φ+λ)} cos(θ/2)]]``.
- Multi-qubit gate matrices are written in the local basis where the FIRST
  operand qubit is the most-significant local bit, e.g.
  ``CX = [[1,0,0,0],[0,1,0,0],[0,0,0,1],[0,0,1,0]]`` for operands
  ``(control, target)``.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .states import QuantumCoreError, DEFAULT_TOLERANCE

_I = np.array([[1, 0], [0, 1]], dtype=np.complex128)
_X = np.array([[0, 1], [1, 0]], dtype=np.complex128)
_Y = np.array([[0, -1j], [1j, 0]], dtype=np.complex128)
_Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)

_PAULIS = {"I": _I, "X": _X, "Y": _Y, "Z": _Z}


def pauli_matrix(name: str) -> np.ndarray:
    try:
        return _PAULIS[name].copy()
    except KeyError:
        raise QuantumCoreError(f"Unknown Pauli {name!r}; expected one of I,X,Y,Z.")


@dataclass(frozen=True)
class GateSpec:
    """A validated quantum gate.

    Attributes:
        name: canonical gate name.
        matrix: unitary matrix of shape (2**n, 2**n).
        n_qubits: operand count.
        n_params: number of real parameters when parameterized (0 otherwise).
    """

    name: str
    matrix: np.ndarray
    n_qubits: int

    def __post_init__(self) -> None:
        m = self.matrix
        if m.ndim != 2 or m.shape[0] != m.shape[1]:
            raise QuantumCoreError(
                f"Gate {self.name!r} matrix must be square, got shape {m.shape}."
            )
        dim = m.shape[0]
        if dim & (dim - 1):
            raise QuantumCoreError(
                f"Gate {self.name!r} dimension must be a power of two, got {dim}."
            )
        expected = 1 << self.n_qubits
        if dim != expected:
            raise QuantumCoreError(
                f"Gate {self.name!r}: dimension {dim} inconsistent with "
                f"{self.n_qubits} qubits (expected {expected})."
            )
        if not is_unitary(m):
            raise QuantumCoreError(
                f"Gate {self.name!r} failed the unitarity check U†U ≈ I."
            )

    @property
    def adjoint(self) -> "GateSpec":
        return GateSpec(self.name + "†", self.matrix.conj().T, self.n_qubits)


def is_unitary(matrix: np.ndarray, tolerance: float = DEFAULT_TOLERANCE) -> bool:
    """Check U†U == I within tolerance (directive §21)."""
    m = np.asarray(matrix, dtype=np.complex128)
    if m.ndim != 2 or m.shape[0] != m.shape[1]:
        return False
    product = m.conj().T @ m
    return bool(np.allclose(product, np.eye(m.shape[0]), atol=tolerance))


# ---------------------------------------------------------------------------
# Single-qubit fixed gates
# ---------------------------------------------------------------------------

_S = np.array([[1, 0], [0, 1j]], dtype=np.complex128)
_SDG = _S.conj().T
_T = np.array([[1, 0], [0, np.exp(1j * np.pi / 4)]], dtype=np.complex128)
_TDAG = _T.conj().T
_H = np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2)

_FIXED_1Q: dict[str, np.ndarray] = {
    "I": _I,
    "X": _X,
    "Y": _Y,
    "Z": _Z,
    "H": _H,
    "S": _S,
    "SDG": _SDG,
    "T": _T,
    "TDG": _TDAG,
}


def rx(theta: float) -> np.ndarray:
    c, s = np.cos(theta / 2), np.sin(theta / 2)
    return np.array([[c, -1j * s], [-1j * s, c]], dtype=np.complex128)


def ry(theta: float) -> np.ndarray:
    c, s = np.cos(theta / 2), np.sin(theta / 2)
    return np.array([[c, -s], [s, c]], dtype=np.complex128)


def rz(theta: float) -> np.ndarray:
    return np.array(
        [[np.exp(-1j * theta / 2), 0], [0, np.exp(1j * theta / 2)]],
        dtype=np.complex128,
    )


def u3(theta: float, phi: float, lam: float) -> np.ndarray:
    ct, st = np.cos(theta / 2), np.sin(theta / 2)
    return np.array(
        [
            [ct, -np.exp(1j * lam) * st],
            [np.exp(1j * phi) * st, np.exp(1j * (phi + lam)) * ct],
        ],
        dtype=np.complex128,
    )


def phase_gate(lam: float) -> np.ndarray:
    return u3(0.0, 0.0, lam)


# ---------------------------------------------------------------------------
# Two- and three-qubit fixed gates (first operand = most significant local bit)
# ---------------------------------------------------------------------------

_CX = np.array(
    [
        [1, 0, 0, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 1],
        [0, 0, 1, 0],
    ],
    dtype=np.complex128,
)

_CZ = np.diag([1, 1, 1, -1]).astype(np.complex128)

_SWAP = np.array(
    [
        [1, 0, 0, 0],
        [0, 0, 1, 0],
        [0, 1, 0, 0],
        [0, 0, 0, 1],
    ],
    dtype=np.complex128,
)

_TOFFOLI = np.eye(8, dtype=np.complex128)
_TOFFOLI[6, 6] = 0.0
_TOFFOLI[7, 7] = 0.0
_TOFFOLI[6, 7] = 1.0
_TOFFOLI[7, 6] = 1.0

_FREDKIN = np.eye(8, dtype=np.complex128)
# |c=1,ab> -> |c=1,ba>: swaps indices 5 (101) and 6 (110)
_FREDKIN[[5, 6], :] = _FREDKIN[[6, 5], :]

_FIXED_2Q: dict[str, np.ndarray] = {
    "CX": _CX,
    "CNOT": _CX,
    "CZ": _CZ,
    "SWAP": _SWAP,
}

_FIXED_3Q: dict[str, np.ndarray] = {
    "CCX": _TOFFOLI,
    "TOFFOLI": _TOFFOLI,
    "CSWAP": _FREDKIN,
    "FREDKIN": _FREDKIN,
}


def controlled_of(base: np.ndarray) -> np.ndarray:
    """Controlled-U for a single-qubit base matrix U (control = MSB)."""
    out = np.eye(4, dtype=np.complex128)
    out[2:, 2:] = base
    return out


def crx(theta: float) -> np.ndarray:
    return controlled_of(rx(theta))


def cry(theta: float) -> np.ndarray:
    return controlled_of(ry(theta))


def crz(theta: float) -> np.ndarray:
    return controlled_of(rz(theta))


def cu3(theta: float, phi: float, lam: float) -> np.ndarray:
    return controlled_of(u3(theta, phi, lam))


# ---------------------------------------------------------------------------
# Parameterized gate registry used by the circuit engine
# ---------------------------------------------------------------------------

PARAMETERIZED_1Q: dict[str, tuple[int, callable]] = {
    # name -> (n_params, builder)
    "RX": (1, lambda p: rx(p[0])),
    "RY": (1, lambda p: ry(p[0])),
    "RZ": (1, lambda p: rz(p[0])),
    "P": (1, lambda p: phase_gate(p[0])),
    "U3": (3, lambda p: u3(p[0], p[1], p[2])),
    "PHASE": (1, lambda p: phase_gate(p[0])),
}

PARAMETERIZED_2Q: dict[str, tuple[int, callable]] = {
    "CRX": (1, lambda p: crx(p[0])),
    "CRY": (1, lambda p: cry(p[0])),
    "CRZ": (1, lambda p: crz(p[0])),
    "CU3": (3, lambda p: cu3(p[0], p[1], p[2])),
    "RZZ": (1, lambda p: _rzz(p[0])),
}


def _rzz(theta: float) -> np.ndarray:
    """exp(-i θ Z⊗Z / 2), operands (q_a, q_b); diag in ZZ basis."""
    d = np.diag(
        [
            np.exp(-1j * theta / 2),
            np.exp(1j * theta / 2),
            np.exp(1j * theta / 2),
            np.exp(-1j * theta / 2),
        ]
    ).astype(np.complex128)
    return d


def build_gate(name: str, params: list[float]) -> GateSpec:
    """Build and validate a gate by canonical name.

    Raises QuantumCoreError with an actionable message for unknown names or
    wrong parameter counts (directive §25, §286).
    """
    name_u = name.upper()
    if name_u in _FIXED_1Q:
        if params:
            raise QuantumCoreError(
                f"Gate {name!r} takes no parameters, got {params}."
            )
        return GateSpec(name_u, _FIXED_1Q[name_u].copy(), 1)
    if name_u in PARAMETERIZED_1Q:
        n, builder = PARAMETERIZED_1Q[name_u]
        return _build_parameterized(name_u, n, builder, params, 1)
    if name_u in _FIXED_2Q:
        if params:
            raise QuantumCoreError(f"Gate {name!r} takes no parameters, got {params}.")
        return GateSpec(name_u, _FIXED_2Q[name_u].copy(), 2)
    if name_u in PARAMETERIZED_2Q:
        n, builder = PARAMETERIZED_2Q[name_u]
        return _build_parameterized(name_u, n, builder, params, 2)
    if name_u in _FIXED_3Q:
        if params:
            raise QuantumCoreError(f"Gate {name!r} takes no parameters, got {params}.")
        return GateSpec(name_u, _FIXED_3Q[name_u].copy(), 3)
    known = sorted(
        set(_FIXED_1Q) | set(_FIXED_2Q) | set(_FIXED_3Q)
        | set(PARAMETERIZED_1Q) | set(PARAMETERIZED_2Q)
    )
    raise QuantumCoreError(
        f"Unknown gate {name!r}. Known gates: {', '.join(known)}."
    )


def _build_parameterized(name, n_params, builder, params, n_qubits) -> GateSpec:
    if len(params) != n_params:
        raise QuantumCoreError(
            f"Gate {name!r} requires {n_params} parameter(s), got {len(params)}: {params}."
        )
    arr = np.asarray(params, dtype=float)
    if not np.all(np.isfinite(arr)):
        raise QuantumCoreError(f"Gate {name!r} parameters must be finite numbers.")
    return GateSpec(name, builder(arr.tolist()), n_qubits)


def custom_gate(name: str, matrix: np.ndarray) -> GateSpec:
    """Wrap a caller-supplied unitary matrix as a validated gate.

    Structured data only — arbitrary user code is never executed here
    (directive §209).
    """
    return GateSpec(name, np.asarray(matrix, dtype=np.complex128), int(np.log2(matrix.shape[0])))


GATE_CATALOG: list[dict] = (
    [{"name": n, "n_qubits": 1, "n_params": 0} for n in sorted(_FIXED_1Q)]
    + [{"name": n, "n_qubits": 1, "n_params": PARAMETERIZED_1Q[n][0]} for n in sorted(PARAMETERIZED_1Q)]
    + [{"name": n, "n_qubits": 2, "n_params": 0} for n in sorted(set(_FIXED_2Q))]
    + [{"name": n, "n_qubits": 2, "n_params": PARAMETERIZED_2Q[n][0]} for n in sorted(PARAMETERIZED_2Q)]
    + [{"name": n, "n_qubits": 3, "n_params": 0} for n in sorted(_FIXED_3Q)]
)
