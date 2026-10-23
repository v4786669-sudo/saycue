"""`python -m saycue` — wejście CLI (W1: audio → ASR, bez GUI)."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
