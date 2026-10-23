"""Normalizacja tekstu PL/EN (pipeline bez LLM, architektura §2.3).

* W1 (eval G1): ``normalize()`` — lowercase, NFKC, interpunkcja, fold PL.
  Funkcja bez zmian — eval G1 dalej jej używa.
* W2 (t13): ``normalize_text()`` — pełny pipeline §2.3 z usuwaniem
  wypełniaczy TYLKO z początku wypowiedzi (fix R-01, t10/t15).
* v0.3 (t15): ``normalize_verbose()`` — diagnostyka ``rewritten_fillers``
  (licznik/tokeny stałego słownika, nigdy treść mowy).
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


def normalize_verbose(
    text: str | None, *, remove_fillers: bool = True
) -> tuple[str, tuple[str, ...]]:
    """Normalizacja + diagnostyka usuniętych wypełniaczy (v0.3 §2.3).

    Zwraca ``(norm, removed_fillers)``. ``removed_fillers`` zawiera WYŁĄCZNIE
    tokeny ze stałego słownika FILLER_TOKENS (nigdy treść mowy) — to pole
    diagnostyczne może trafić do logów/telemetrii bez ryzyka prywatności.
    """
    if not text:
        return "", ()
    norm = normalize(text)
    removed: list[str] = []
    if remove_fillers and norm:
        words = norm.split()
        while words and words[0] in FILLER_TOKENS:
            removed.append(words.pop(0))
        norm = " ".join(words)
    return norm, tuple(removed)


def normalize_text(text: str | None, *, remove_fillers: bool = True) -> str:
    """Pełna normalizacja §2.3: ``normalize`` + usunięcie zwrotów
    „proszę / hej / asystent / ok".

    WAŻNE (fix R-01): fillery usuwane TYLKO z początku wypowiedzi
    („hej, proszę otwórz spotify" → „otworz spotify"). Usuwanie w środku/
    na końcu potrafi zostawić goły token (np. „…na spotkanie o 8" → „o"),
    który trafia w fragment frazy. Całe tokeny, nie podciągi („skok"
    zostaje „skok").

    Zwraca ``""`` dla pustego/None. Idempotentna.
    """
    return normalize_verbose(text, remove_fillers=remove_fillers)[0]


def fuzzy_similarity(a: str, b: str) -> float:
    """Podobieństwo 0–1 znormalizowanych tekstów (difflib; rapidfuzz w W2)."""
    from difflib import SequenceMatcher

    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()
