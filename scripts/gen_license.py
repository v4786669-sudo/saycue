#!/usr/bin/env python3
"""Generuje podpisaną licencję SayCue: UUID + Ed25519, offline.

    python scripts/gen_license.py --product starter --issued-to "ktoś@x.pl"
    python scripts/gen_license.py --product streamer --expires 2027-01-31 --out license.json

- `--expires` puste/null = licencja jednorazowa; data = subskrypcja.
- Klucz prywatny: scripts/.keys/signing_key (NIE w repo).
- Weryfikacja u klienta jest OFFLINE (pubkey wbudowany) — bez device-binding.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import nacl.signing

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / "scripts" / ".keys" / "signing_key"
sys.path.insert(0, str(ROOT / "src"))

from saycue.licensing.crypto import sign_payload  # noqa: E402

PRODUCTS = ("starter", "pro", "streamer")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--product", required=True, choices=PRODUCTS)
    ap.add_argument("--issued-to", required=True, help="adres e-mail / identyfikator klienta")
    ap.add_argument("--expires", default=None, help="ISO data (subskrypcja); brak = jednorazowa")
    ap.add_argument("--out", default="license.json")
    args = ap.parse_args()

    if not PRIVATE.is_file():
        print(f"Brak klucza prywatnego ({PRIVATE}) — najpierw: python scripts/gen_keypair.py")
        return 1
    key = nacl.signing.SigningKey(PRIVATE.read_bytes())

    payload = {
        "license_id": str(uuid.uuid4()),
        "product": args.product,
        "issued_to": args.issued_to,
        "issued_at": datetime.now(UTC).date().isoformat(),
        "expires": args.expires,
    }
    if args.expires:
        try:
            date.fromisoformat(args.expires)
        except ValueError:
            print(f"--expires {args.expires!r} nie jest datą ISO (YYYY-MM-DD)")
            return 1
    payload["signature"] = sign_payload({k: v for k, v in payload.items() if k != "signature"}, key)
    out = Path(args.out)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Licencja: {out}  (license_id={payload['license_id']}, product={args.product}, "
        f"expires={args.expires or 'bezterminowa'})"
    )
    print("Weryfikacja u klienta: offline, bez wiązania z urządzeniem (threat-model §4).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
