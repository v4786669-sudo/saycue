"""Parser intencji — deterministyczny pipeline bez LLM (architektura §2.3).

normalizacja PL → Aho-Corasick (dokładne frazy) → rapidfuzz (fuzzy ≥ 0.78)
→ ekstrakcja slotów z YAML/szablonów → ParseResult(name, slots, score, matches).

W1 dostarczał tylko ``normalize()`` (eval G1). W2 (t13): pełny matcher,
loader rdzenia i presetów (JSON Schema) oraz ``IntentParser`` z hot-reload.
"""

from __future__ import annotations

from .matcher import Matcher
from .normalize import (
    FILLER_TOKENS,
    fold_diacritics,
    normalize,
    normalize_text,
    normalize_verbose,
)
from .pipeline import IntentParser
from .presets import Preset, PresetError, PresetLoader
from .rules import (
    ConfigStore,
    PollingWatcher,
    RulesConfig,
    RulesLoader,
    ValidationError,
    WatchdogWatcher,
    load_apps,
    load_commands,
    load_yaml,
    validate_doc,
)
from .types import Candidate, ParseResult

__all__ = [
    "Candidate",
    "ConfigStore",
    "FILLER_TOKENS",
    "IntentParser",
    "Matcher",
    "ParseResult",
    "PollingWatcher",
    "Preset",
    "PresetError",
    "PresetLoader",
    "RulesConfig",
    "RulesLoader",
    "ValidationError",
    "WatchdogWatcher",
    "fold_diacritics",
    "load_apps",
    "load_commands",
    "load_yaml",
    "normalize",
    "normalize_text",
    "normalize_verbose",
    "validate_doc",
]
