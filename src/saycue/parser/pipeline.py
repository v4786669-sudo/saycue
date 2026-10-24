"""Gotowy do podpięcia parser intencji: rdzeń + aktywne presety + hot-reload.

Punkt integracji dla orchestratora:

    from saycue.parser import IntentParser
    parser = IntentParser(active_presets=["obs-core", "apps-open", "apps-streaming"])
    result = parser.parse(tekst)          # ParseResult | None
    parser.set_active_presets(["obs-core", "apps-open", "elite-dangerous"])

Aktywacja: rdzeń (data/commands.yaml) + wskazane presety — jedna gra +
obs-core + apps-* naraz; kolizje fraz rozstrzyga kolejność aktywacji.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from .matcher import Matcher
from .presets import PresetLoader
from .rules import ConfigStore, RulesConfig, RulesLoader
from .types import Candidate, ParseResult

log = logging.getLogger(__name__)


class IntentParser:
    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        presets_dir: Path | None = None,
        active_presets: list[str] | None = None,
        fuzzy_threshold: float = 0.78,
        min_action_score: float = 0.8,
        min_phrase_coverage: float = 0.7,
        allow_free_text: bool = True,
        watch: bool = False,
        watcher_cls: type | None = None,
        on_reload: Callable[[RulesConfig], None] | None = None,
    ):
        self.loader = RulesLoader(data_dir)
        self.preset_loader = PresetLoader(presets_dir)
        self.active_presets: list[str] = list(active_presets or [])
        self.fuzzy_threshold = float(fuzzy_threshold)
        # R-02/R-01 ( §2.3): progi utwardzenia przekazywane do Matchera
        self.min_action_score = float(min_action_score)
        self.min_phrase_coverage = float(min_phrase_coverage)
        self.allow_free_text = bool(allow_free_text)
        self._lock = threading.Lock()
        self._matcher: Matcher | None = None
        self._config: RulesConfig | None = None
        self._on_reload = on_reload
        self.reload()
        self.store: ConfigStore | None = None
        if watch:
            self.store = ConfigStore(
                self.loader,
                watcher_cls=watcher_cls,
                on_change=self._on_config,
            )
            self._on_reload = on_reload

    # -------------------------------------------------------------- (re)build

    def reload(self) -> IntentParser:
        cfg = self.loader.load(self.active_presets, self.preset_loader)
        self._apply_config(cfg)
        return self

    def set_active_presets(self, preset_ids: list[str]) -> IntentParser:
        """Podmienia zestaw aktywnych presetów i przebudowuje matcher."""
        self.active_presets = list(preset_ids)
        return self.reload()

    def _apply_config(self, cfg: RulesConfig) -> None:
        matcher = Matcher(
            cfg.commands,
            cfg.apps,
            fuzzy_threshold=self.fuzzy_threshold,
            min_action_score=self.min_action_score,
            min_phrase_coverage=self.min_phrase_coverage,
            allow_free_text=self.allow_free_text,
        )
        with self._lock:
            self._config = cfg
            self._matcher = matcher
        log.info(
            "gramatyka załadowana: %d komend (presety: %s)",
            len(cfg.commands),
            ",".join(cfg.active_presets) or "-",
        )

    def _on_config(self, cfg: RulesConfig) -> None:
        self._apply_config(cfg)
        if self._on_reload is not None:
            self._on_reload(cfg)

    # ------------------------------------------------------------------ parse

    def parse(self, text: str | None) -> ParseResult | None:
        with self._lock:
            matcher = self._matcher
        if matcher is None:
            return None
        return matcher.parse(text)

    def candidates(self, text: str | None, k: int = 3) -> list[Candidate]:
        with self._lock:
            matcher = self._matcher
        if matcher is None:
            return []
        return matcher.candidates(text, k=k)

    @property
    def config(self) -> RulesConfig | None:
        with self._lock:
            return self._config

    def close(self) -> None:
        if self.store is not None:
            self.store.stop()
