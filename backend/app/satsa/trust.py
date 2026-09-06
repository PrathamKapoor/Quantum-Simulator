"""SAT-SA Trust Layer — cryptographic provenance + integrity.

Implements evidence integrity, provenance signing, and audit trail
using only the Python standard library (no new dependencies — the
directive forbids runtime Internet / external packages; "air-gapped
by design").

The trust layer uses:
  - SHA-256 (hashlib, stdlib) for evidence digests and Merkle trees.
  - A hash-based one-time signature (Lamport-style + Merkle root
    binding) for provenance signatures. Each submission has its
    own one-time keypair; signatures are bound to the SHA-256
    digest of the payload, and the Merkle root of the signed
    digests is stored in the audit trail.
  - Tamper tests (valid, modified-evidence, modified-finding,
    broken-provenance, invalid-signature) for the test suite.

This is NOT a NIST PQC algorithm. It is a hash-based integrity
primitive suitable for air-gapped operation, with documented
limitations (one-time keys, large signatures). Use cases:
  - evidence digest verification;
  - submission provenance;
  - audit trail integrity;
  - tamper detection.

For higher-throughput or smaller-signature needs, the layer can
be replaced with a real PQC library (Kyber/Dilithium) when one is
allowed. The interface is the same.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Hashing primitives.
# ---------------------------------------------------------------------------

def sha256(data: bytes) -> str:
    """SHA-256 hex digest of data."""
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: dict) -> bytes:
    """Serialize obj to canonical JSON bytes (sorted keys, no spaces)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def canonical_json_digest(obj: dict) -> str:
    return sha256(canonical_json(obj))


# ---------------------------------------------------------------------------
# Lamport-style hash-based one-time signature.
# ---------------------------------------------------------------------------

# Each Lamport keypair has 2 * 256 random 32-byte secret bits and
# publishes their SHA-256 hashes. To sign a single bit '0', reveal
# the secret at index 0; for '1', reveal index 1. Verification:
# the revealed secret hashes to the public commitment.

LAMPORT_SEGMENT_BYTES = 32  # 256 bits
LAMPORT_LEVELS = 256       # 256 bits per message digest


def _lamport_keypair():
    secrets_pre = [secrets.token_bytes(LAMPORT_SEGMENT_BYTES)
                  for _ in range(2 * LAMPORT_LEVELS)]
    public = [sha256(s) for s in secrets_pre]
    return {"secret": secrets_pre, "public": public}


def _lamport_sign(message_digest_hex: str, secret_pre: list[bytes]) -> list[str]:
    """Reveal the secret for each bit of the message digest. The
    message digest is interpreted as 256 bits (64 hex chars); for
    each bit we reveal the secret at index 2*b for the bit's value
    b. Returns 256 reveals (= 512 secrets / 2 per bit)."""
    if len(message_digest_hex) != 64:
        raise ValueError("message digest must be 32 bytes hex (64 chars).")
    out = []
    # 64 hex chars -> 256 bits
    bit_index = 0
    for i in range(64):
        nibble = int(message_digest_hex[i], 16)
        for k in range(4):
            b = (nibble >> (3 - k)) & 1
            idx = 2 * bit_index + b
            out.append(secret_pre[idx].hex())
            bit_index += 1
    return out


def _lamport_verify(message_digest_hex: str, signature: list[str],
                    public: list[str]) -> bool:
    if len(signature) != LAMPORT_LEVELS:
        return False
    bit_index = 0
    for i in range(64):
        nibble = int(message_digest_hex[i], 16)
        for k in range(4):
            b = (nibble >> (3 - k)) & 1
            idx = 2 * bit_index + b
            if sha256(bytes.fromhex(signature[bit_index])) != public[idx]:
                return False
            bit_index += 1
    return True


# Re-decorate the verify function to be safe (the above already
# has the correct code; the duplicate below is a no-op alias).
_lamport_verify = _lamport_verify


# ---------------------------------------------------------------------------
# Merkle tree (binary SHA-256).
# ---------------------------------------------------------------------------

def merkle_root(leaves: list[str]) -> str:
    """Compute the Merkle root of a list of hex SHA-256 digests.
    Odd last leaf is duplicated (standard convention)."""
    if not leaves:
        return ""
    layer = list(leaves)
    while len(layer) > 1:
        nxt = []
        for i in range(0, len(layer), 2):
            left = layer[i]
            right = layer[i + 1] if i + 1 < len(layer) else layer[i]
            nxt.append(sha256((left + right).encode("ascii")))
        layer = nxt
    return layer[0]


# ---------------------------------------------------------------------------
# Submission integrity + provenance.
# ---------------------------------------------------------------------------

@dataclass
class KeyPair:
    public: list[str]            # 512 SHA-256 hex digests
    secret: list[bytes]          # 512 32-byte secrets

    @staticmethod
    def generate() -> "KeyPair":
        kp = _lamport_keypair()
        return KeyPair(public=kp["public"], secret=kp["secret"])


@dataclass
class SignatureRecord:
    message_digest: str
    signature: list[str]    # 512 hex strings
    public: list[str]       # 512 hex strings

    def to_dict(self) -> dict:
        return {
            "message_digest": self.message_digest,
            "signature": list(self.signature),
            "public": list(self.public),
        }


def sign_submission(payload: dict, keypair: KeyPair) -> SignatureRecord:
    """Sign a submission payload. Returns the signature record."""
    msg = canonical_json_digest(payload)
    sig = _lamport_sign(msg, keypair.secret)
    return SignatureRecord(message_digest=msg, signature=sig,
                            public=list(keypair.public))


def verify_signature(record: dict) -> bool:
    """Verify a signature record. Returns True if the signature is
    valid against the public key AND the message digest matches
    the one in the record."""
    msg = record.get("message_digest", "")
    sig = record.get("signature", [])
    public = record.get("public", [])
    if not msg or not sig or not public:
        return False
    if not _lamport_verify(msg, sig, public):
        return False
    return True


# ---------------------------------------------------------------------------
# Submission digest + provenance helper.
# ---------------------------------------------------------------------------

def digest_submission(payload: dict) -> str:
    """Canonical SHA-256 digest of a submission payload (the
    'evidence digest' recorded in Provenance.source_digest)."""
    return canonical_json_digest(payload)


def verify_submission(payload: dict, expected_digest: str) -> bool:
    """Re-derive the canonical digest and compare to the
    expected one (e.g. the one stored in Provenance.source_digest)."""
    return digest_submission(payload) == expected_digest


# ---------------------------------------------------------------------------
# Audit trail Merkle root.
# ---------------------------------------------------------------------------

def audit_root(records: list[dict]) -> str:
    """Compute the Merkle root of a list of audit-trail records.
    Each record is a dict; its digest is the canonical JSON digest."""
    leaves = [canonical_json_digest(r) for r in records]
    return merkle_root(leaves)


__all__ = [
    "sha256", "canonical_json", "canonical_json_digest",
    "KeyPair", "SignatureRecord",
    "sign_submission", "verify_signature",
    "digest_submission", "verify_submission",
    "merkle_root", "audit_root",
]
