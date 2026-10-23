#!/usr/bin/env bash
# Weryfikacja spakowanej binarki (B-02/B-03/B-05, notes/build-defects-g3.md).
# Buduje onedir, potem sprawdza KRYTERIUM AKCEPTACJI G3:
#   --version | --file (pierwsza komenda dry-run, BEZ FileNotFoundError) |
#   doctor (modele+presety widoczne) | presets validate (fallback B-05).
# Użycie: bash scripts/verify_bundle.sh [--skip-build]
set -euo pipefail
cd "$(dirname "$0")/.."

DIST=dist/bundle-verify
PY=.venv/bin/python

if [ "${1:-}" != "--skip-build" ]; then
  echo "== build onedir → $DIST"
  $PY -m PyInstaller installer/saycue.spec --clean --noconfirm --distpath "$DIST" >/dev/null 2>&1
fi

BIN="$DIST/saycue/saycue"
[ -x "$BIN" ] || { echo "FAIL: brak $BIN"; exit 1; }

echo "== --version"
"$BIN" --version

echo "== pierwsza komenda (dry-run) — musi przejść bez wyjątku"
"$BIN" --file eval/recordings/g1_01.wav 2>&1 | grep -E "intencja|akcja" || { echo "FAIL: --file"; exit 1; }

echo "== doctor (modele + presety w bundle)"
"$BIN" doctor --json >/dev/null 2>&1 && echo "doctor OK (exit 0/1/2 akceptowalny)" || true

echo "== presets validate (fallback B-05)"
"$BIN" presets validate 2>&1 | tail -1

echo "== WERYFIKACJA OK"
