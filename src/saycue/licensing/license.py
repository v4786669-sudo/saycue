"""Licencja SayCue: podpisany JSON, weryfikacja offline, bez device-binding.

Przykład (generowane przez `scripts/gen_license.py`):

    {
      "license_id": "f8c9…uuid", "product": "starter",
      "issued_to": "ktoś@example.com", "issued_at": "2026-10-24",
      "expires": null,               # null = jednorazowa; data = subskrypcja
      "signature": "base64(Ed25519 kanonicznego JSON pól bez signature)"
    }

Weryfikacja: `load_license(path)` → `License` (lub LicenseError /
LicenseExpiredError). Żadnego wiązania z urządzeniem ani aktywacji online —
obietnica „100% offline" (PLAN §3, threat-model §4).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from .crypto import verify_payload
from .keys import default_verify_key

PRODUCTS = ("starter", "pro", "streamer")

_FIELDS = ("license_id", "product", "issued_to", "issued_at", "expires")


class LicenseError(ValueError):
    """Licencja nieczytelna, bez podpisu lub z nieprawidłowym podpisem."""


class LicenseExpiredError(LicenseError):
    """Licencja ważna, ale wygasła (subskrypcja po terminie)."""


@dataclass(frozen=True)
class License:
    license_id: str
    product: str
    issued_to: str
    issued_at: str
    expires: str | None  # ISO data (null = jednorazowa)

    @property
    def is_expired(self) -> bool:
        if not self.expires:
            return False
        try:
            return date.fromisoformat(self.expires) < date.today()
        except ValueError:
            return True  # niezrozumiała data = nie ryzykujemy

    @property
    def is_subscription(self) -> bool:
        return self.expires is not None


def _payload(data: dict[str, Any]) -> dict[str, Any]:
    return {field: data.get(field) for field in _FIELDS}


def load_license(path: Path, verify_key=None) -> License:
    """Wczytuje i weryfikuje licencję (podpis + termin). Podnosi LicenseError."""
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LicenseError(f"licencja nieczytelna: {path}") from exc
    if not isinstance(raw, dict):
        raise LicenseError("licencja nie jest obiektem JSON")

    signature = raw.get("signature")
    payload = _payload(raw)
    if not all(payload.get(f) for f in ("license_id", "product", "issued_to", "issued_at")):
        raise LicenseError("licencja niekompletna (brak wymaganych pól)")
    if payload["product"] not in PRODUCTS:
        raise LicenseError(f"nieznany produkt: {payload['product']!r}")
    try:
        uuid.UUID(str(payload["license_id"]))
    except ValueError as exc:
        raise LicenseError("license_id nie jest UUID") from exc

    verifier = verify_key or default_verify_key()
    if not signature or not verify_payload(payload, str(signature), verifier):
        raise LicenseError("podpis licencji nieprawidłowy (plik zmodyfikowany lub sfałszowany)")

    license_ = License(
        license_id=str(payload["license_id"]),
        product=str(payload["product"]),
        issued_to=str(payload["issued_to"]),
        issued_at=str(payload["issued_at"]),
        expires=payload.get("expires"),
    )
    if license_.is_expired:
        raise LicenseExpiredError(
            f"licencja {license_.license_id} wygasła ({license_.expires}) — odnow subskrypcję"
        )
    return license_


def _today_iso() -> str:
    return datetime.now(UTC).date().isoformat()
