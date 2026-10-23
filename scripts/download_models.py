#!/usr/bin/env python3
"""Pobiera modele SayCue z manifestu (models/manifest.json) + weryfikuje SHA-256.

Ryzyko R10: wagi NIGDY nie trafiają do repo — tylko manifest z URL i sumami.
Cache: ~/.cache/saycue/models/ (platformdirs).
Tryby:
    python scripts/download_models.py            # pobierz brakujące + zweryfikuj
    python scripts/download_models.py --verify   # tylko weryfikacja
    python scripts/download_models.py --pin      # przelicz SHA-256 pobranych plików
                                                 # i zapisz manifest (modele zaufane)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from saycue.asr.manifest import (  # noqa: E402
    MANIFEST_REPO_PATH,
    ModelSpec,
    check_manifest_consistency,
    load_manifest,
    model_path,
    sha256_file,
    verify_all,
)
from saycue.config.paths import models_dir  # noqa: E402

CHUNK = 1 << 20


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with tmp.open("wb") as f:
            for chunk in r.iter_content(CHUNK):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r  {dest.name}: {done / 1e6:.0f}/{total / 1e6:.0f} MB", end="")
        print()
    tmp.replace(dest)


def download_spec(spec: ModelSpec) -> None:
    print(f"[{spec.id}] {spec.url}")
    if spec.kind == "single-file":
        rel = next(iter(spec.files))
        dest = model_path(spec, rel)
        if dest.is_file() and sha256_file(dest) == spec.files[rel]:
            print(f"  ok (w cache): {dest}")
            return
        download(spec.url, dest)
        actual = sha256_file(dest)
        expect = spec.files[rel]
        if expect != "PENDING" and actual != expect:
            raise SystemExit(
                f"  BŁĄD SHA-256 dla {spec.id}: oczekiwano {expect}, jest {actual}. "
                "Plik usunięty — sprawdź manifest."
            )
        print(
            f"  pobrano ({actual[:16]}…)"
            + (" [suma do przypięcia]" if expect == "PENDING" else " ok SHA-256")
        )
    elif spec.kind == "multi-file":
        base = spec.url.rstrip("/")
        all_ok = True
        for rel, sha in spec.files.items():
            dest = model_path(spec, rel)
            if dest.is_file() and sha != "PENDING" and sha256_file(dest) == sha:
                continue
            all_ok = False
            if dest.is_file() and sha != "PENDING" and sha256_file(dest) != sha:
                dest.unlink()  # uszkodzony plik → pobierz ponownie
            download(f"{base}/{rel}", dest)
            actual = sha256_file(dest)
            if sha != "PENDING" and actual != sha:
                raise SystemExit(f"  BŁĄD SHA-256 dla {rel}: oczekiwano {sha}, jest {actual}.")
        if all_ok:
            print("  ok (w cache)")
    else:
        raise SystemExit(f"nieznany kind: {spec.kind}")


def pin_manifest() -> None:
    """Przelicza SHA-256 lokalnych plików (krok 2 — po zaufanym pobraniu).

    UWAGA: używaj TYLKO na świeżo pobranych, zaufanych plikach."""
    raw = json.loads(MANIFEST_REPO_PATH.read_text(encoding="utf-8"))
    for entry in raw["models"]:
        if entry["kind"] == "single-file":
            p = models_dir() / entry["id"] / entry["file"]
            if not p.is_file():
                print(f"pominięto {entry['id']} (brak pliku w cache)")
                continue
            entry["sha256"] = sha256_file(p)
            entry["size_mb"] = round(p.stat().st_size / 1e6)
            print(f"pinned {entry['id']}: {entry['sha256'][:16]}…")
        elif entry["kind"] == "multi-file":
            missing = [
                f["file"]
                for f in entry["files"]
                if not (models_dir() / entry["id"] / f["file"]).is_file()
            ]
            if missing:
                print(f"pominięto {entry['id']} (brak w cache: {', '.join(missing)})")
                continue
            total = 0
            for f in entry["files"]:
                p = models_dir() / entry["id"] / f["file"]
                f["sha256"] = sha256_file(p)
                total += p.stat().st_size
                print(f"pinned {entry['id']}/{f['file']}: {f['sha256'][:16]}…")
            entry["size_mb"] = round(total / 1e6)
    MANIFEST_REPO_PATH.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n")
    # kopia wbudowana w pakiet (CI pilnuje identyczności)
    bundled = Path(__file__).resolve().parents[1] / "src" / "saycue" / "data" / "manifest.json"
    bundled.write_text(MANIFEST_REPO_PATH.read_text(encoding="utf-8"))
    print(f"manifest zaktualizowany: {MANIFEST_REPO_PATH} + kopia w pakiecie")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true", help="tylko weryfikacja SHA-256")
    ap.add_argument("--pin", action="store_true", help="przelicz SHA-256 i zapisz manifest")
    ap.add_argument("--only", help="id modelu (np. whisper-small)")
    args = ap.parse_args()

    if args.pin:
        pin_manifest()
        check_manifest_consistency()
        print("spójność manifestów: OK")
        return 0

    specs = load_manifest()
    if args.only:
        specs = {args.only: specs[args.only]}

    for spec in specs.values():
        if args.verify:
            ok, msg = verify_all(specs)[spec.id]
            print(f"[{spec.id}] {'ok' if ok else 'PROBLEM: ' + msg}")
            if not ok:
                return 1
        else:
            download_spec(spec)

    if not args.verify:
        print("\nWeryfikacja:")
        failed = False
        for sid, (ok, msg) in verify_all(specs).items():
            print(f"  [{sid}] {'ok' if ok else 'PROBLEM: ' + msg}")
            failed = failed or not ok
        if failed:
            return 1
    print("\nModele gotowe w:", models_dir())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
