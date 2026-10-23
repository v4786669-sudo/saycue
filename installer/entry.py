"""Punkt wejścia dla PyInstaller (instalator) — import absolutny, bez pakietu-nadrzędnego."""

import sys

from saycue.cli import main

if __name__ == "__main__":
    sys.exit(main())
