"""Podpis manifestu presetów (supply-chain): `presets/index.json.sig`.

Sygnatura Ed25519 (klucz SayCue) liczona z SUROWYCH bajtów index.json
(detached signature — format manifestu zostaje nietknięty). Loader presetów
weryfikuje go przed załadowaniem paczek: zmieniony manifest = odmowa.
To ochrona przed wstrzyknięciem złośliwego presetu (threat-model §4 pkt 2).
"""

from __future__ import annotations

import base64
from pathlib import Path

import nacl.exceptions

from .keys import default_verify_key


def sign_index(index_path: Path, signing_key) -> bytes:
    """Zwraca sygnaturę (bajty) dla zawartości index_path."""
    return signing_key.sign(index_path.read_bytes()).signature


def verify_index_signature(
    index_path: Path,
    sig_path: Path | None = None,
    verify_key=None,
) -> bool:
    """True, gdy index.json.sig zgadza się z zawartością index.json."""
    index_path = Path(index_path)
    sig_path = Path(sig_path) if sig_path else index_path.with_suffix(index_path.suffix + ".sig")
    if not index_path.is_file() or not sig_path.is_file():
        return False
    try:
        raw = base64.b64decode(sig_path.read_text(encoding="ascii").strip(), validate=True)
        verifier = verify_key or default_verify_key()
        verifier.verify(index_path.read_bytes(), raw)
        return True
    except (OSError, ValueError, nacl.exceptions.BadSignatureError):
        return False
