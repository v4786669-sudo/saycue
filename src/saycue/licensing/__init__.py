"""Licencje SayCue — Ed25519, offline, BEZ wiązania z urządzeniem.

Kontrakt:
- **licencja = podpisany JSON**: `license_id` (UUID, unikalny — śledzenie
  wycieków, nie blokuje offline), `product` (starter/pro/streamer),
  `expires` (null = jednorazowa, data = subskrypcja), `issued_to`;
- **weryfikacja OFFLINE**: klucz publiczny wbudowany w aplikację
  (`saycue/licensing/pubkey.pem`); żadnego device-binding, żadnej
  aktywacji online — to jawna decyzja projektowa (obietnica „100% offline");
- Ed25519 to **integralność + proweniencja**, nie anty-piractwo: w open core
  klient-side check jest z definicji obejściowy (threat-model §3);
- ten sam klucz podpisuje **manifest presetów** (`presets/index.json.sig`) —
  ochrona supply-chain przed złośliwym presetem (największy ROI, §4 pkt 2).

Klucze: surowe 32 bajty Ed25519 (format PyNaCl). Prywatny NIGDY w repo
(`scripts/.keys/`, .gitignore); publiczny w `saycue/licensing/pubkey.pem`.
Generacja: `python scripts/gen_keypair.py`; licencje: `scripts/gen_license.py`.
"""

from .crypto import (
    InvalidSignatureError,
    canonical_bytes,
    sign_payload,
    verify_payload,
)
from .keys import default_verify_key, public_key_bytes
from .license import (
    PRODUCTS,
    License,
    LicenseError,
    LicenseExpiredError,
    load_license,
)
from .manifest import verify_index_signature

__all__ = [
    "PRODUCTS",
    "License",
    "LicenseError",
    "LicenseExpiredError",
    "InvalidSignatureError",
    "canonical_bytes",
    "default_verify_key",
    "load_license",
    "public_key_bytes",
    "sign_payload",
    "verify_index_signature",
    "verify_payload",
]
