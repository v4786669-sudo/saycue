"""`python -m saycue` — wejście CLI (audio → ASR, bez GUI)."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
