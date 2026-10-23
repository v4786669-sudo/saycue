"""Pomocniczy współczynnik podobieństwa (rapidfuzz, fallback: difflib)."""

from __future__ import annotations

try:
    from rapidfuzz import fuzz as _rf

    def ratio(a: str, b: str) -> float:
        """Podobieństwo 0.0–1.0 (rapidfuzz.fuzz.ratio / 100)."""
        return _rf.ratio(a, b) / 100.0

except ImportError:  # pragma: no cover - środowiska bez rapidfuzz
    import difflib

    def ratio(a: str, b: str) -> float:
        return difflib.SequenceMatcher(None, a, b).ratio()
