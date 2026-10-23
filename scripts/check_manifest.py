#!/usr/bin/env python3
"""CI: sprawdza spójność i kompletność models/manifest.json (ryzyko R10).

Wymagania:
- format 1, każdy model ma URL i pełne sumy SHA-256 (64 znaki hex),
- kopia wbudowana w pakiet == manifest w repo (brak dryfu),
- w katalogu models/ nie ma plików binarnych (wagi nigdy w repo).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from saycue.asr.manifest import check_manifest_consistency  # noqa: E402

SHA_RE = re.compile(r"^[0-9a-f]{64}$")
BIN_SUFFIXES = {".bin", ".onnx", ".pt", ".pth", ".safetensors", ".gguf", ".tar.gz", ".zip"}


def main() -> int:
    problems: list[str] = []
    try:
        check_manifest_consistency()
    except Exception as exc:
        problems.append(str(exc))

    manifest_path = ROOT / "models" / "manifest.json"
    if not manifest_path.is_file():
        problems.append("brak models/manifest.json")
        return _report(problems)
    import json

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    for entry in raw.get("models", []):
        mid = entry.get("id", "?")
        if not entry.get("url"):
            problems.append(f"{mid}: brak URL")
        if entry["kind"] == "single-file":
            if not SHA_RE.match(entry.get("sha256", "")):
                problems.append(f"{mid}: brak/niepełne sha256")
        elif entry["kind"] == "multi-file":
            for f in entry.get("files", []):
                if not SHA_RE.match(f.get("sha256", "")):
                    problems.append(f"{mid}/{f.get('file')}: brak/niepełne sha256")

    # wagi nie mogą trafić do repo
    for p in (ROOT / "models").rglob("*"):
        if p.is_file() and p.suffix.lower() in BIN_SUFFIXES:
            problems.append(f"waga w repo (R10): {p.relative_to(ROOT)}")
    return _report(problems)


def _report(problems: list[str]) -> int:
    if problems:
        print("MANIFEST FAIL:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("MANIFEST OK — wszystkie modele mają URL + SHA-256, wagi poza repo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
