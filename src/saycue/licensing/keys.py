"""Klucz publiczny SayCue — wbudowany w aplikację (weryfikacja offline)."""

from __future__ import annotations

import sys
from importlib import resources
from pathlib import Path

import nacl.signing

_PUBKEY_FILE = "pubkey.pem"


def public_key_bytes() -> bytes:
    """Surowe 32 bajty klucza publicznego Ed25519 (PyNaCl)."""
    # tryb dev: plik obok modułu; bundle: importlib.resources (saycue/licensing)
    local = Path(__file__).resolve().parent / _PUBKEY_FILE
    if local.is_file():
        return local.read_bytes()
    base = getattr(sys, "_MEIPASS", None)
    if base is not None:
        candidate = Path(base) / "saycue" / "licensing" / _PUBKEY_FILE
        if candidate.is_file():
            return candidate.read_bytes()
    return resources.files("saycue.licensing").joinpath(_PUBKEY_FILE).read_bytes()


def default_verify_key() -> nacl.signing.VerifyKey:
    """Klucz weryfikujący z zasobu wbudowanego (publiczny — nie jest tajemnicą)."""
    return nacl.signing.VerifyKey(public_key_bytes())
