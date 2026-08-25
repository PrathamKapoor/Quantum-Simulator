"""QuantumLab quantum core package.

Conventions (binding for the entire platform, directive §18):

- **Qubit ordering is little-endian**: qubit 0 is the least-significant bit of a
  computational-basis index. An n-qubit basis state is written
  ``|q_{n-1} ... q_1 q_0>`` and its index is ``sum_k q_k * 2**k``.
- ``tensor(a, b)`` places ``a``'s qubits at the HIGH-order positions
  (numpy kron semantics: index = i_a * dim_b + i_b).
- Angles are radians everywhere unless a field name explicitly says otherwise.
- All complex arithmetic uses numpy complex128.
"""
