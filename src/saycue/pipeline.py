"""Kompatybilność W1: Pipeline = Orchestrator bez parsera/akcji (t6).

Od t9 kanoniczna jest maszyna stanów w `orchestrator.py` (§2.1).
Ten moduł zostaje jako cienka warstwa zgodności dla kodu z W1
(cli, tests/test_pipeline_loop.py) i zniknie po przejściu GUI (W3).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .orchestrator import Orchestrator, Outcome


@dataclass
class PipelineResult:
    text: str
    asr_ms: float
    end_to_end_ms: float
    trigger: str
    audio_seconds: float


class Pipeline(Orchestrator):
    """Orchestrator z callbackiem W1 `on_result` (sam tekst, bez akcji)."""

    def __init__(
        self,
        asr,
        capture,
        vad,
        wake=None,
        ptt=None,
        pre_roll_s: float = 0.4,
        end_silence_s: float = 0.6,
        max_utterance_s: float = 8.0,
        on_result: Callable[[PipelineResult], None] | None = None,
        debug_audio_dir: Path | None = None,
        **kwargs,
    ):
        def _on_outcome(o: Outcome) -> None:
            if on_result is not None:
                on_result(
                    PipelineResult(
                        text=o.text,
                        asr_ms=o.asr_ms,
                        end_to_end_ms=o.e2e_total_ms,
                        trigger=o.trigger,
                        audio_seconds=o.audio_seconds,
                    )
                )

        super().__init__(
            asr=asr,
            capture=capture,
            vad=vad,
            wake=wake,
            ptt=ptt,
            pre_roll_s=pre_roll_s,
            end_silence_s=end_silence_s,
            max_utterance_s=max_utterance_s,
            on_outcome=_on_outcome,
            debug_audio_dir=debug_audio_dir,
            **kwargs,
        )
