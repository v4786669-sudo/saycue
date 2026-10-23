"""Testy walidatora presetów — negatywne przypadki. Uruchomienie:

    python3 presets/test_validate.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATE = HERE / "validate.py"
OBS = HERE / "obs-core"


def run(target: Path) -> tuple[int, str]:
    # Pojedynczy preset podajemy jako jedyny argument (walidator przyjmuje katalog z preset.yaml).
    # Dla walidacji zbiorczej nie podajemy argumentów wcale.
    args = [sys.executable, str(VALIDATE)] + ([] if target == HERE else [str(target)])
    proc = subprocess.run(args, capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def case_dir(tmp: Path, name: str) -> Path:
    dst = tmp / name
    shutil.copytree(OBS, dst)
    # popraw id, żeby nie łapać S2 dla przypadków testujących inną regułę
    yamls = dst / "preset.yaml"
    yamls.write_text(yamls.read_text(encoding="utf-8").replace("id: obs-core", f"id: {name}"), encoding="utf-8")
    return dst


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="saycue-presets-"))
    checks: list[tuple[str, bool, str]] = []
    try:
        code, out = run(HERE)
        checks.append(("wszystkie presety przechodzą", code == 0 and "0 błędów" in out, out[-300:]))

        d = case_dir(tmp, "evil-code")
        (d / "evil.py").write_text("print(1)\n", encoding="utf-8")
        code, out = run(d)
        checks.append(("odrzuca plik .py w presecie", code != 0 and "S3" in out, out[-200:]))

        d = case_dir(tmp, "bad-slot")
        y = d / "preset.yaml"
        y.write_text(y.read_text(encoding="utf-8").replace('slots: { scene: "Live" }', 'slots: { target: "nope" }', 1),
                     encoding="utf-8")
        code, out = run(d)
        checks.append(("odrzuca slot niezgodny z intencją", code != 0 and "S6" in out, out[-200:]))

        d = case_dir(tmp, "dup-phrase")
        y = d / "preset.yaml"
        y.write_text(y.read_text(encoding="utf-8").replace('phrases: ["scena pvp",', 'phrases: ["scena live",', 1),
                     encoding="utf-8")
        code, out = run(d)
        checks.append(("odrzuca duplikat frazy", code != 0 and "S4" in out, out[-200:]))

        d = case_dir(tmp, "too-many")
        y = d / "preset.yaml"
        original = y.read_text(encoding="utf-8")
        needle = 'phrases: ["scena live"'
        assert needle in original, "mutacja testu nie trafiła w frazy obs_scene_live"
        # dopisz szóstą frazę (do limitu) — siódma ma złamać schemat
        mutated = original.replace(
            'phrases: ["scena live", "przełącz na live", "daj live", "scene live", "live scene"]',
            'phrases: ["scena live", "przełącz na live", "daj live", "scene live", "live scene", "lajf", "scena lejw"]',
            1)
        assert mutated != original, "druga mutacja nie zadziałała"
        y.write_text(mutated, encoding="utf-8")
        code, out = run(d)
        checks.append(("odrzuca >6 fraz", code != 0 and ("S1" in out or "S4" in out), out[-300:]))

        d = case_dir(tmp, "extra-field")
        y = d / "preset.yaml"
        y.write_text(y.read_text(encoding="utf-8").replace("  - id: obs_scene_live\n", "  - extra: 1\n    id: obs_scene_live\n", 1),
                     encoding="utf-8")
        code, out = run(d)
        checks.append(("odrzuca pole spoza schematu", code != 0 and "S1" in out, out[-200:]))

        code, out = run(HERE)
        code_j, out_j = run(HERE)
        checks.append(("walidacja zbiorcza z --json", code_j == 0 and "OK" in out_j, out_j[-200:]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = 0
    for name, ok, detail in checks:
        print(("OK   " if ok else "FAIL ") + name)
        if not ok:
            failed += 1
            print("      " + detail.replace("\n", "\n      "))
    print(f"\n{len(checks) - failed}/{len(checks)} sprawdzeń")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
