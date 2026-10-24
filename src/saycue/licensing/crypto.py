"""Ed25519: podpisywanie i weryfikacja (PyNaCl) — format kanoniczny JSON.

Sygnatura liczona z kanonicznej reprezentacji pól
(`json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=True)`),
kodowana base64. Weryfikacja offline — bez sieci, bez device-binding.
"""

from __future__ import annotations

import base64
import json
from typing import Any

import nacl.exceptions
import nacl.signing


class InvalidSignatureError(ValueError):
    """Podpis nie zgadza się z treścią (lub nieczytelny)."""


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """Kanoniczna reprezentacja JSON (deterministyczna — podstawa podpisu)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "utf-8"
    )


def sign_payload(payload: dict[str, Any], signing_key: nacl.signing.SigningKey) -> str:
    """Podpisuje kanoniczny JSON — zwraca base64 sygnatury."""
    signed = signing_key.sign(canonical_bytes(payload))
    return base64.b64encode(signed.signature).decode("ascii")


def verify_payload(payload: dict[str, Any], signature_b64: str, verify_key) -> bool:
    """Sprawdza sygnaturę kanonicznego JSON. False = treść lub podpis zmienione."""
    if not signature_b64:
        return False
    try:
        raw = base64.b64decode(signature_b64, validate=True)
        verify_key.verify(canonical_bytes(payload), raw)
        return True
    except (ValueError, TypeError, nacl.exceptions.BadSignatureError):
        return False
