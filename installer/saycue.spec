# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — SayCue (onedir, architektura §6 W3).

Budowa Windows:  pyinstaller installer/windows/saycue.spec --clean
(W CI: .github/workflows/build-windows.yml → Inno Setup → saycue-setup.exe)
Budowa Linux:    pyinstaller installer/saycue.spec
Modele NIE są w bundle'u (R10) — pierwsze uruchomienie pobiera je z manifestu
(python -m saycue doctor podpowie)."""
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 — SPECPATH = katalog ze spec (installer/)

hiddenimports = [
    "saycue.data",
    "openwakeword", "faster_whisper", "ctranslate2", "av", "onnxruntime",
    "pynput", "yaml", "platformdirs", "requests", "websockets",
]
# GUI opcjonalne: bez nich app działa jako CLI (doctor/demo)
try:
    import PySide6  # noqa: F401

    hiddenimports += ["PySide6.QtWidgets", "PySide6.QtGui", "PySide6.QtCore"]
    try:
        import pystray  # noqa: F401

        hiddenimports.append("pystray")
    except ImportError:
        pass
except ImportError:
    pass

a = Analysis(
    [str(ROOT / "installer" / "entry.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    # R-BUILD-01: manifest modeli + presety MUSZĄ być w bundle'u — loader używa
    # importlib.resources od 'saycue.data' (saycue/asr/manifest.py:84,126), więc bez tego
    # instalator zgłasza "No module named 'saycue.data'" po instalacji.
    datas=[
        (str(ROOT / "src" / "saycue" / "data" / "manifest.json"), "saycue/data"),
        (str(ROOT / "presets"), "presets"),
        # R-BUILD-02: rdzeń gramatyki i mapowanie aplikacji — loader czyta je z katalogu danych
        # (saycue/parser/rules.py:240,244; saycue/actions/app_open.py:53). Bez tego instalator
        # wykłada się na pierwszej komendzie: "data/commands.yaml: No such file".
        (str(ROOT / "data" / "commands.yaml"), "data"),
        (str(ROOT / "data" / "apps.yaml"), "data"),
        # B-02c: schematy JSON parsera (commands/apps) — walidacja w rules.py
        (str(ROOT / "src" / "saycue" / "parser" / "schemas"), "saycue/parser/schemas"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "ruff"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="saycue",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    icon=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="saycue",
)
