"""Normalizacja tekstu PL/EN (pipeline bez LLM, architektura §2.3).

* W1 (eval G1): ``normalize()`` — lowercase, NFKC, interpunkcja, fold PL.
  Funkcja bez zmian — eval G1 dalej jej używa.
* W2 (t13): ``normalize_text()`` — pełny pipeline §2.3, dodatkowo usuwa
  zwroty grzecznościowe („proszę / hej / asystent / ok"). Matcher fraz
  (``parser/matcher.py``) używa ``normalize_text``.
"""

from __future__ import annotations

import re
import unicodedata

# ą→a, ć→c, ę→e, ł→l, ń→n, ó→o, ś→s, ź→z, ż→z
_PL_FOLD = str.maketrans("ąćęłńóśźż", "acelnoszz")

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")

# Zwroty grzecznościowe usuwane w kroku 3 §2.3 (już po foldzie diakrytyków).
FILLER_TOKENS = frozenset({"prosze", "hej", "asystent", "ok"})


def fold_diacritics(text: str) -> str:
    """NFKC + polskie mapowanie diakrytyków (§2.3 krok 1–2)."""
    return unicodedata.normalize("NFKC", text).translate(_PL_FOLD)


def normalize(text: str) -> str:
    """Lowercase → NFKC → usuń interpunkcję → fold PL → scal białe znaki.

    Wersja W1 (kroki 1–2 z §2.3), używana przez eval G1. Bez zmian.
    """
    text = unicodedata.normalize("NFKC", text).lower()
    text = _PUNCT_RE.sub(" ", text)
    text = fold_diacritics(text)
    return _SPACE_RE.sub(" ", text).strip()


def normalize_text(text: str | None, *, remove_fillers: bool = True) -> str:
    """Pełna normalizacja §2.3: ``normalize`` + usunięcie zwrotów
    „proszę / hej / asystent / ok" (całe tokeny, nie podciągi — „skok"
    zostaje „skok").

    Zwraca ``""`` dla pustego/None. Idempotentna.
    """
    if not text:
        return ""
    norm = normalize(text)
    if remove_fillers and norm:
        norm = " ".join(w for w in norm.split() if w not in FILLER_TOKENS)
    return norm


def fuzzy_similarity(a: str, b: str) -> float:
    """Podobieństwo 0–1 znormalizowanych tekstów (difflib; rapidfuzz w W2)."""
    from difflib import SequenceMatcher

    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()
