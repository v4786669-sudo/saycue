"""Testy doctora: werdykty, modele, OBS (błąd bez serwera), FAQ, offline."""

from __future__ import annotations

import pytest

from saycue.doctor import (
    CheckResult,
    check_models,
    check_obs,
    check_offline,
    check_wakeword_fp,
    format_checks,
    generate_faq,
    verdict,
)

pytestmark = pytest.mark.skipif(
    not __import__("importlib.util", fromlist=["find_spec"]).find_spec("PySide6"),
    reason="bez wpływu — testy czystego doctora",
)


def test_verdict_mapping():
    assert verdict([CheckResult("a", "ok", "")]) == (0, "wszystko OK")
    assert verdict([CheckResult("a", "warn", "")])[0] == 1
    assert verdict([CheckResult("a", "error", "")])[0] == 2
    assert verdict([CheckResult("a", "error", ""), CheckResult("b", "warn", "")])[0] == 2


def test_check_models_verify_manifest(tmp_path, monkeypatch):
    from collections import namedtuple

    _Usage = namedtuple("usage", ["total", "used", "free"])
    monkeypatch.setattr("saycue.doctor.shutil.disk_usage", lambda p: _Usage(1e12, 5e11, 5e11))
    results = check_models()
    assert results, "brak wyników check_models"
    ids = {r.name: r.status for r in results}
    assert ids["modele"] in ("ok", "error")  # ok gdy cache jest, error bez pobrania
    for r in results:
        assert r.fix if r.status != "ok" else True  # każdy problem ma naprawę


def test_check_obs_error_without_server():
    result = check_obs(obs_url="127.0.0.1:1")  # port zamknięty → błąd + naprawa
    assert result.status == "error"
    assert "OBS" in result.fix


def test_check_wakeword_fp_ok():
    result = check_wakeword_fp()
    assert result.status in ("ok", "warn")


def test_check_offline_requires_models(monkeypatch):
    result = check_offline()
    assert result.status in ("ok", "warn")
    # komunikat zależy od stanu cache: „wszystkie modele lokalne… offline"
    # albo „brak modeli w cache…" — sprawdzamy, że mówi o modelach i ma naprawę
    assert "model" in result.message
    if result.status == "warn":
        assert result.fix


def test_format_checks_has_fix_lines():
    out = format_checks(
        [
            CheckResult("x", "error", "zepsute", "napraw to"),
            CheckResult("y", "ok", "działa"),
        ]
    )
    assert "napraw to" in out
    assert "✓" in out and "✗" in out


def test_generate_faq_contains_sections(tmp_path):
    faq = generate_faq(events_path=tmp_path / "e.jsonl")
    assert "# FAQ — SayCue" in faq
    assert "## OBS" in faq
    assert "## Wayland" in faq
    assert "Najczęstsze 5 problemów" in faq
