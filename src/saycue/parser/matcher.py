"""Dopasowywanie tekstu do intencji: Aho-Corasick (dokładne) + rapidfuzz (fuzzy).

Zasady (architektura §2.3):
* deterministycznie — ten sam tekst = ten sam intent;
* dokładne trafienie frazy → score 1.0; fuzzy ≥ 0.78; mniej → brak (ASK);
* konflikt: wygrywa dłuższa fraza, remis → kolejność definicji;
* sloty dynamiczne: frazy-szablony ``otwórz {app}`` — wartość slotu wycinana
  z tekstu i rozwiązywana po słowniku (aplikacje/sceny) z fuzzy ≥ 0.78;
* kolizje fraz między źródłami (rdzeń vs aktywne presety) rozstrzyga loader
  (``rules.py``) — matcher widzi już spójną, zdeduplikowaną listę komend.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .fuzzy import ratio as _ratio
from .normalize import normalize_text
from .slots import SlotResolver, build_slot_vocabs
from .types import Candidate, ParseResult

try:
    import ahocorasick as _ahocorasick
except ImportError:  # pragma: no cover - fallback dla środowisk bez C-extension
    _ahocorasick = None

log = logging.getLogger(__name__)

_TEMPLATE_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


@dataclass
class _ExactEntry:
    command: dict[str, Any]
    phrase: str  # znormalizowana fraza
    original: str
    order: int


@dataclass
class _TemplateEntry:
    command: dict[str, Any]
    prefix: str
    suffix: str
    slot: str
    original: str
    order: int


def _parse_template(original: str) -> tuple[str, str, str] | None:
    """(prefix, suffix, slot) dla frazy z jednym slotem ``{name}``; None bez slotu."""
    found = list(_TEMPLATE_RE.finditer(original))
    if not found:
        return None
    if len(found) > 1:
        raise ValueError(f"fraza szablonowa może mieć tylko jeden slot: {original!r}")
    m = found[0]
    prefix = normalize_text(original[: m.start()])
    suffix = normalize_text(original[m.end() :])
    return prefix, suffix, m.group(1)


class _NaiveAutomaton:
    """Fallback O(n·m) gdy pyahocorasick niedostępny (ten sam interfejs)."""

    def __init__(self, groups: Mapping[str, tuple[int, ...]]):
        self._groups = dict(groups)

    def iter(self, text: str) -> Iterator[tuple[int, tuple[int, ...]]]:
        for phrase, indices in self._groups.items():
            start = 0
            while True:
                pos = text.find(phrase, start)
                if pos < 0:
                    break
                yield pos + len(phrase), indices
                start = pos + 1


class Matcher:
    """Gramatyka deklaratywna: dokładne frazy + szablony slotów + fuzzy."""

    def __init__(
        self,
        commands: Sequence[Mapping[str, Any]],
        apps: Mapping[str, Any] | None = None,
        *,
        fuzzy_threshold: float = 0.78,
    ):
        self.fuzzy_threshold = float(fuzzy_threshold)
        self.apps: dict[str, Any] = dict(apps or {})
        self._exact: list[_ExactEntry] = []
        self._templates: list[_TemplateEntry] = []
        order = 0
        for cmd in commands:
            for phrase in cmd.get("phrases") or []:
                original = str(phrase)
                tpl = _parse_template(original)
                norm = normalize_text(original)
                if tpl is None:
                    self._exact.append(_ExactEntry(cmd, norm, original, order))
                else:
                    self._templates.append(
                        _TemplateEntry(cmd, tpl[0], tpl[1], tpl[2], original, order)
                    )
                order += 1
        self._vocabs = build_slot_vocabs(commands, self.apps)
        self._resolver = SlotResolver(self._vocabs, threshold=self.fuzzy_threshold)
        self._automaton = self._build_automaton()

    # ------------------------------------------------------------------ build

    def _build_automaton(self):
        groups: dict[str, tuple[int, ...]] = {}
        for idx, entry in enumerate(self._exact):
            groups.setdefault(entry.phrase, ())
            groups[entry.phrase] = groups[entry.phrase] + (idx,)
        if _ahocorasick is None:
            return _NaiveAutomaton(groups)
        automaton = _ahocorasick.Automaton()
        for phrase, indices in groups.items():
            automaton.add_word(phrase, indices)
        automaton.make_automaton()
        return automaton

    # ------------------------------------------------------------------- parse

    def parse(self, text: str | None) -> ParseResult | None:
        norm = normalize_text(text or "")
        if not norm:
            return None
        exact = self._match_exact(norm)
        if exact is not None:
            entry, matched = exact
            return self._result(entry.command, matched, 1.0, "exact")
        tpl = self._match_template(norm)
        if tpl is not None:
            entry, raw, resolved = tpl
            slots = dict(entry.command.get("slots") or {})
            if resolved is not None:
                slots[entry.slot] = resolved
                score = 1.0
            else:
                slots[entry.slot] = raw
                score = 0.9
            return ParseResult(
                intent=entry.command["intent"],
                slots=slots,
                score=score,
                matched=(entry.original,),
                source="template",
                command_id=entry.command["id"],
                origin=entry.command.get("origin", "core"),
            )
        fuzzy = self._match_fuzzy(norm)
        if fuzzy is None:
            return None
        entry, score = fuzzy
        return self._result(entry.command, entry.phrase, round(score, 3), "fuzzy")

    def _result(
        self, command: Mapping[str, Any], matched: str, score: float, source: str
    ) -> ParseResult:
        return ParseResult(
            intent=command["intent"],
            slots=dict(command.get("slots") or {}),
            score=score,
            matched=(matched,),
            source=source,
            command_id=command["id"],
            origin=command.get("origin", "core"),
        )

    def _match_exact(self, norm: str) -> tuple[_ExactEntry, str] | None:
        best: dict[int, tuple[_ExactEntry, str]] = {}
        for _end, indices in self._automaton.iter(norm):
            for idx in indices:
                entry = self._exact[idx]
                if idx not in best or len(entry.phrase) > len(best[idx][1]):
                    best[idx] = (entry, entry.phrase)
        if not best:
            return None
        return max(best.values(), key=lambda pair: (len(pair[1]), -pair[0].order))

    def _match_template(self, norm: str) -> tuple[_TemplateEntry, str, Any | None] | None:
        for entry in self._templates:
            if not norm.startswith(entry.prefix):
                continue
            rest = norm[len(entry.prefix) :]
            if rest and not rest[0].isspace():
                continue  # wymagamy granicy słowa za prefiksem
            raw = rest.strip()
            if entry.suffix:
                if not raw.endswith(entry.suffix):
                    continue
                before = raw[: len(raw) - len(entry.suffix)]
                if before and not before[-1].isspace():
                    continue
                raw = before.strip()
            if not raw:
                continue
            resolved = self._resolver.resolve(entry.slot, raw)
            return entry, raw, resolved
        return None

    def _match_fuzzy(self, norm: str) -> tuple[_ExactEntry, float] | None:
        ranked: list[tuple[float, _ExactEntry]] = []
        for entry in self._exact:
            ranked.append((_ratio(norm, entry.phrase), entry))
        ranked.sort(
            key=lambda pair: (round(pair[0], 4), len(pair[1].phrase), -pair[1].order),
            reverse=True,
        )
        best_score, best = ranked[0]
        if best_score < self.fuzzy_threshold:
            return None
        return best, best_score

    # ------------------------------------------------------------ candidates

    def candidates(self, text: str | None, k: int = 3) -> list[Candidate]:
        """Najlepsze kandydatury dla widoku ASK (w tym poniżej progu fuzzy)."""
        norm = normalize_text(text or "")
        out: list[Candidate] = []
        if norm:
            # dokładne trafienia (Aho-Corasick; unikalna, najdłuższa fraza na komendę)
            seen_exact: dict[int, _ExactEntry] = {}
            for _end, indices in self._automaton.iter(norm):
                for idx in indices:
                    entry = self._exact[idx]
                    if idx not in seen_exact or len(entry.phrase) > len(seen_exact[idx].phrase):
                        seen_exact[idx] = entry
            for entry in seen_exact.values():
                out.append(
                    Candidate(
                        command_id=entry.command["id"],
                        intent=entry.command["intent"],
                        slots=dict(entry.command.get("slots") or {}),
                        phrase=entry.phrase,
                        original=entry.original,
                        score=1.0,
                        source="exact",
                        origin=entry.command.get("origin", "core"),
                        order=entry.order,
                    )
                )
            tpl = self._match_template(norm)
            if tpl is not None:
                entry, raw, resolved = tpl
                slots = dict(entry.command.get("slots") or {})
                slots[entry.slot] = resolved if resolved is not None else raw
                out.append(
                    Candidate(
                        command_id=entry.command["id"],
                        intent=entry.command["intent"],
                        slots=slots,
                        phrase=entry.original,
                        original=entry.original,
                        score=1.0 if resolved is not None else 0.9,
                        source="template",
                        origin=entry.command.get("origin", "core"),
                        order=entry.order,
                    )
                )
            for entry in self._exact:
                out.append(
                    Candidate(
                        command_id=entry.command["id"],
                        intent=entry.command["intent"],
                        slots=dict(entry.command.get("slots") or {}),
                        phrase=entry.phrase,
                        original=entry.original,
                        score=round(_ratio(norm, entry.phrase), 3),
                        source="fuzzy",
                        origin=entry.command.get("origin", "core"),
                        order=entry.order,
                    )
                )
        out.sort(key=lambda c: (round(c.score, 4), len(c.phrase), -c.order), reverse=True)
        deduped: list[Candidate] = []
        seen = set()
        for cand in out:
            key = (cand.command_id, cand.source)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(cand)
        return deduped[:k]
