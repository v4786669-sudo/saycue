#!/usr/bin/env python3
"""Generuje parę kluczy Ed25519 SayCue.

- prywatny: scripts/.keys/signing_key  (NIGDY nie commitować — .gitignore)
- publiczny: src/saycue/licensing/pubkey.pem  (commitowany; wbudowany w aplikację)

UWAGA: zgubienie klucza prywatnego = niemożność podpisania kolejnych
licencji/manifestów. Po wygenerowaniu zrób backup poza repozytorium.

    python scripts/gen_keypair.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import nacl.signing

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "scripts" / ".keys" / "signing_key"
PUBLIC = ROOT / "src" / "saycue" / "licensing" / "pubkey.pem"


def main() -> int:
    if PRIVATE.is_file():
        print(f"Klucz prywatny już istnieje ({PRIVATE}) — odmawiam nadpisania.")
        print(
            "Backup usuń ręcznie, jeśli NAPRAWDĘ chcesz nową parę (stare licencje przestaną działać)."
        )
        return 1
    key = nacl.signing.SigningKey.generate()
    PRIVATE.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE.write_bytes(bytes(key))
    PUBLIC.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC.write_bytes(bytes(key.verify_key))
    print(f"Klucz prywatny:  {PRIVATE}  (NIE commitować; zrób backup!)")
    print(f"Klucz publiczny: {PUBLIC} (commitowany)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
