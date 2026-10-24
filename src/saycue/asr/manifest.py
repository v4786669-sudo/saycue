"""Pobieranie modeli z manifestu + weryfikacja SHA-256 (ryzyko R10).

Modele NIGDY nie trafiają do repo — tylko manifest `models/manifest.json`
z URL-ami i sumami SHA-256. Wagi lądują w katalogu cache użytkownika
(`~/.cache/saycue/models/`), pobierane wyłącznie przez jawną komendę
`python scripts/download_models.py`.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from ..config.paths import models_dir, repo_root

MANIFEST_REPO_PATH = repo_root() / "models" / "manifest.json"
MANIFEST_BUNDLED = "saycue.data.manifest.json"
CHUNK = 1 << 20


class ManifestError(Exception):
    """Błąd manifestu: nieprawidłowy format, brak pliku lub suma SHA-256 się nie zgadza."""


@dataclass(frozen=True)
class ModelSpec:
    id: str
    kind: str
    url: str
    files: dict[str, str]  # relative path -> sha256
    license: str = "MIT"
    size_mb: int = 0
    notes: str = ""
    sha256: str = ""  # pojedynczy plik (kind="single-file")
    extra: dict = field(default_factory=dict)


def _parse(raw: dict) -> dict[str, ModelSpec]:
    fmt = raw.get("format")
    if fmt != 1:
        raise ManifestError(f"nieobsługiwany format manifestu: {fmt!r} (oczekiwano 1)")
    specs: dict[str, ModelSpec] = {}
    for entry in raw.get("models", []):
        if entry["kind"] == "single-file":
            specs[entry["id"]] = ModelSpec(
                id=entry["id"],
                kind=entry["kind"],
                url=entry["url"],
                files={entry["file"]: entry["sha256"]},
                license=entry.get("license", "MIT"),
                size_mb=entry.get("size_mb", 0),
                notes=entry.get("notes", ""),
            )
        elif entry["kind"] == "multi-file":
            files = {f["file"]: f["sha256"] for f in entry["files"]}
            specs[entry["id"]] = ModelSpec(
                id=entry["id"],
                kind=entry["kind"],
                url=entry["url"],
                files=files,
                license=entry.get("license", "MIT"),
                size_mb=entry.get("size_mb", 0),
                notes=entry.get("notes", ""),
                extra={
                    "model": entry.get("model"),
                    "language": entry.get("language"),
                    "engine": entry.get("engine"),
                },
            )
        else:
            raise ManifestError(f"nieznany kind modelu: {entry.get('kind')!r}")
    return specs


def load_manifest() -> dict[str, ModelSpec]:
    """Manifest z repo (dev) lub kopii wbudowanej w pakiet (instalacja)."""
    if MANIFEST_REPO_PATH.is_file():
        raw = json.loads(MANIFEST_REPO_PATH.read_text(encoding="utf-8"))
    else:
        bundled = resources.files("saycue.data").joinpath("manifest.json")
        raw = json.loads(bundled.read_text(encoding="utf-8"))
    return _parse(raw)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def model_path(spec: ModelSpec, file: str) -> Path:
    return models_dir() / spec.id / file


def verify_spec(spec: ModelSpec) -> tuple[bool, str]:
    """Sprawdza obecność i sumy SHA-256 wszystkich plików modelu w cache."""
    missing = []
    for rel in spec.files:
        p = model_path(spec, rel)
        if not p.is_file():
            missing.append(rel)
            continue
        actual = sha256_file(p)
        if actual != spec.files[rel]:
            return (
                False,
                f"{spec.id}/{rel}: SHA-256 niezgodny (oczekiwano {spec.files[rel][:12]}…, jest {actual[:12]}…)",
            )
    if missing:
        return False, f"{spec.id}: brak plików w cache: {', '.join(missing)}"
    return True, ""


def verify_all(specs: dict[str, ModelSpec]) -> dict[str, tuple[bool, str]]:
    return {sid: verify_spec(spec) for sid, spec in specs.items()}


def check_manifest_consistency() -> None:
    """CI: kopia w pakiecie == manifest w repo (żadnego dryfu)."""
    bundled = resources.files("saycue.data").joinpath("manifest.json")
    bundled_text = bundled.read_text(encoding="utf-8")
    if MANIFEST_REPO_PATH.is_file():
        repo_text = MANIFEST_REPO_PATH.read_text(encoding="utf-8")
        if bundled_text != repo_text:
            raise ManifestError(
                "models/manifest.json różni się od kopii w pakiecie "
                "(src/saycue/data/manifest.json) — zsynchronizuj je."
            )
    # sanity: pliki manifestu muszą mieć sumy SHA-256 (R10)
    for sid, spec in _parse(json.loads(bundled_text)).items():
        for rel, sha in spec.files.items():
            if len(sha) != 64 or not all(c in "0123456789abcdef" for c in sha):
                raise ManifestError(
                    f"model {sid}/{rel}: brak lub niepełna suma SHA-256 (R10) — "
                    "pobierz modele i uruchom: python scripts/download_models.py --pin"
                )


if __name__ == "__main__":
    check_manifest_consistency()
    print("manifest OK", file=sys.stderr)
