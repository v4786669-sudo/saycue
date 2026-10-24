#!/usr/bin/env python3
"""Podpisuje manifest presetów (presets/index.json → index.json.sig).

Supply-chain: loader presetów ładuje paczki TYLKO, gdy podpis manifestu się
zgadza (wstrzyknięcie złośliwego presetu = odmowa). Ten sam klucz Ed25519 co
licencje. Po KAŻDYM `python presets/validate.py` (regeneruje index.json)
uruchom ponownie ten skrypt.

    python scripts/sign_presets_index.py            # podpisz
    python scripts/sign_presets_index.py --verify   # tylko sprawdź (CI)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import nacl.signing

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "presets" / "index.json"
SIG = INDEX.with_suffix(INDEX.suffix + ".sig")
PRIVATE = ROOT / "scripts" / ".keys" / "signing_key"
sys.path.insert(0, str(ROOT / "src"))

from saycue.licensing.manifest import verify_index_signature  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--verify", action="store_true", help="tylko weryfikacja (bez klucza prywatnego)"
    )
    ap.add_argument("--index", default=str(INDEX), help="ścieżka index.json")
    ap.add_argument("--sig", default=str(SIG), help="ścieżka pliku .sig")
    args = ap.parse_args()

    index, sig = Path(args.index), Path(args.sig)
    if args.verify:
        ok = verify_index_signature(index, sig)
        print(
            f"{'OK — podpis zgodny' if ok else 'FAIL — manifest zmodyfikowany lub niepodpisany'}: {index}"
        )
        return 0 if ok else 1

    if not PRIVATE.is_file():
        print(f"Brak klucza prywatnego ({PRIVATE}) — najpierw: python scripts/gen_keypair.py")
        return 1
    if not index.is_file():
        print(f"Brak {index}")
        return 1
    key = nacl.signing.SigningKey(PRIVATE.read_bytes())
    signature = key.sign(index.read_bytes()).signature
    import base64

    sig.write_text(base64.b64encode(signature).decode("ascii") + "\n", encoding="ascii")
    print(f"Podpisano: {index} → {sig}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
