"""Testy licencji: Ed25519 offline, bez wiązania z urządzeniem; wygasła blokuje."""

from __future__ import annotations

import json
from pathlib import Path

import nacl.signing
import pytest

from saycue.licensing.crypto import canonical_bytes, sign_payload, verify_payload
from saycue.licensing.license import (
    LicenseError,
    LicenseExpiredError,
    load_license,
)


@pytest.fixture
def keypair():
    key = nacl.signing.SigningKey.generate()
    return key, key.verify_key


def make_license(key, **overrides):
    payload = {
        "license_id": "123e4567-e89b-42d3-a456-426614174000",
        "product": "starter",
        "issued_to": "ktoś@example.com",
        "issued_at": "2026-10-24",
        "expires": None,
    }
    payload.update(overrides)
    payload["signature"] = sign_payload(payload, key)
    return payload


def write_license(tmp_path: Path, payload: dict, name="license.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_valid_license_loads(tmp_path, keypair):
    key, verify = keypair
    path = write_license(tmp_path, make_license(key))
    lic = load_license(path, verify_key=verify)
    assert lic.license_id == "123e4567-e89b-42d3-a456-426614174000"
    assert lic.product == "starter"
    assert lic.expires is None and not lic.is_expired and not lic.is_subscription


def test_subscription_license_expiry(tmp_path, keypair):
    key, verify = keypair
    path = write_license(tmp_path, make_license(key, product="streamer", expires="2020-01-01"))
    with pytest.raises(LicenseExpiredError):
        load_license(path, verify_key=verify)
    path2 = write_license(
        tmp_path, make_license(key, product="streamer", expires="2999-01-01"), "l2.json"
    )
    lic = load_license(path2, verify_key=verify)
    assert lic.is_subscription and not lic.is_expired


def test_tampered_field_rejected(tmp_path, keypair):
    key, verify = keypair
    payload = make_license(key)
    payload["product"] = "pro"  # podmiana pola po podpisaniu
    path = write_license(tmp_path, payload)
    with pytest.raises(LicenseError, match="podpis"):
        load_license(path, verify_key=verify)


def test_missing_signature_rejected(tmp_path, keypair):
    key, verify = keypair
    payload = make_license(key)
    del payload["signature"]
    path = write_license(tmp_path, payload)
    with pytest.raises(LicenseError, match="podpis"):
        load_license(path, verify_key=verify)


def test_wrong_key_rejected(tmp_path, keypair):
    key, _verify = keypair
    other = nacl.signing.SigningKey.generate()
    path = write_license(tmp_path, make_license(key))
    with pytest.raises(LicenseError, match="podpis"):
        load_license(path, verify_key=other.verify_key)


def test_unknown_product_rejected(tmp_path, keypair):
    key, verify = keypair
    path = write_license(tmp_path, make_license(key, product="deluxe"))
    with pytest.raises(LicenseError, match="produkt"):
        load_license(path, verify_key=verify)


def test_non_uuid_license_id_rejected(tmp_path, keypair):
    key, verify = keypair
    path = write_license(tmp_path, make_license(key, license_id="nie-uuid"))
    with pytest.raises(LicenseError, match="UUID"):
        load_license(path, verify_key=verify)


def test_canonical_json_deterministic():
    a = {"b": 1, "a": "x"}
    b = {"a": "x", "b": 1}
    assert canonical_bytes(a) == canonical_bytes(b)


def test_verify_payload_roundtrip(keypair):
    key, verify = keypair
    sig = sign_payload({"x": 1}, key)
    assert verify_payload({"x": 1}, sig, verify)
    assert not verify_payload({"x": 2}, sig, verify)
    assert not verify_payload({"x": 1}, "", verify)
