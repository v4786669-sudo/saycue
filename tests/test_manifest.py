"""Testy manifestu modeli (R10: URL + SHA-256, wagi poza repo)."""

from saycue.asr.manifest import (
    check_manifest_consistency,
    load_manifest,
)


def test_manifest_loads_and_has_sha256():
    specs = load_manifest()
    assert "whisper-small" in specs
    assert "openwakeword-alexa" in specs
    for sid, spec in specs.items():
        assert spec.url.startswith("https://"), sid
        assert spec.files, sid
        for rel, sha in spec.files.items():
            assert len(sha) == 64 and all(c in "0123456789abcdef" for c in sha), f"{sid}/{rel}"


def test_bundled_copy_matches_repo():
    check_manifest_consistency()
