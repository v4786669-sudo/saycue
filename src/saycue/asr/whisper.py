"""ASR: faster-whisper `small` int8, PL domyślnie, beam=1, initial_prompt.

Decyzje:
- `small` multilingual — domyślny model MVP (PL+EN w jednym modelu),
- `compute_type="int8"` na CPU (GPU: auto `float16`, patrz `auto_compute_type`),
- `beam_size=1` (greedy) dla latencji, `beam_size=5` tylko w trybie dokładnym (GUI, W3),
- `initial_prompt` = lista fraz z `commands.yaml` (zmniejsza „twórcze" transkrypcje),
- `temperature=0` — determinizm (ten sam plik = ten sam wynik),
- `word_timestamps=False`, `condition_on_previous_text=False` — minimalny koszt.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..audio.capture import SAMPLE_RATE
from ..config.paths import data_dir

log = logging.getLogger(__name__)

DEFAULT_MODEL = "small"
DEFAULT_LANGUAGE = "pl"
DEFAULT_BEAM = 1
DEFAULT_CPU_THREADS = 4


@dataclass
class ASRResult:
    text: str
    elapsed_s: float
    language: str
    language_probability: float
    audio_seconds: float


def load_phrases(commands_yaml: Path | None = None) -> list[str]:
    """Wszystkie frazy z commands.yaml (PL) — źródło promptu i hotwords.

    Szablony ze slotami („otwórz {target}") są pomijane — nawiasy nie pomagają
    promptowi, a W2 rozwiązuje je dynamicznie."""
    import yaml

    path = commands_yaml or data_dir() / "commands.yaml"
    if not path.is_file():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    phrases: list[str] = []
    for cmd in raw.get("commands", []):
        for phrase in cmd.get("phrases", []):
            phrase = str(phrase).strip()
            if "{" not in phrase and phrase:
                phrases.append(phrase)
    return phrases


def filter_short_phrases(phrases, max_tokens: int = 2) -> list[str]:
    """Filtruje frazy do promptu: bez szablonów slotów, ≤ max_tokens tokenów.

    Pułapka zmierzona (G2): prompt ze WSZYSTKICH fraz aktywnych
    presetów (~220) DEGENERUJE greedy decoding (14/20) — bias tylko krótkich
    fraz jest bezpieczny (rdzeń + arcade-dash ≈ dawny zestaw: 16–17/20)."""
    out: list[str] = []
    for phrase in phrases:
        phrase = str(phrase).strip()
        if not phrase or "{" in phrase:
            continue
        if len(phrase.split()) <= max_tokens and phrase not in out:
            out.append(phrase)
    return out


def load_initial_prompt(
    commands_yaml: Path | None = None,
    extra_phrases: list[str] | None = None,
    max_phrases: int = 60,
) -> str:
    """Rdzeń (commands.yaml) + KRÓTKIE frazy aktywnych presetów → initial_prompt.

    Cap `max_phrases` to twarde zabezpieczenie przed degeneracją greedy
    (zmierzone: ~220 fraz → 14/20 G2; ~35 fraz → 17–19/20)."""
    phrases = list(load_phrases(commands_yaml))
    extras = filter_short_phrases(extra_phrases or [])
    for phrase in extras:
        if phrase not in phrases:
            phrases.append(phrase)
    return ", ".join(phrases[:max_phrases])


def load_hotwords(commands_yaml: Path | None = None) -> str:
    """Słowa z pola `hotwords` w commands.yaml → bias tokenów (faster-whisper ≥1.2).

    Tylko jawna, krótka lista (≤3 słowa): biasowanie WSZYSTKICH fraz degeneruje
    greedy decoding w pętle powtórzeń (zmierzone w G1)."""
    import yaml

    path = commands_yaml or data_dir() / "commands.yaml"
    if not path.is_file():
        return ""
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    words = [str(w).strip() for w in raw.get("hotwords", [])]
    return ", ".join(w for w in words if w)


def auto_compute_type() -> str:
    """int8 na CPU; float16, gdy dostępna CUDA (CTranslate2 bez PyTorcha)."""
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "float16"
    except Exception:
        pass
    return "int8"


class ASREngine:
    def __init__(
        self,
        model_dir: Path | None = None,
        model_size: str = DEFAULT_MODEL,
        compute_type: str = "auto",
        language: str = DEFAULT_LANGUAGE,
        beam_size: int = DEFAULT_BEAM,
        cpu_threads: int = DEFAULT_CPU_THREADS,
        initial_prompt: str | None = None,
        hotwords: str | None = None,
        no_speech_threshold: float = 0.6,
        hallucination_silence_threshold: float | None = None,
    ):
        self.model_size = model_size
        self.language = language
        self.beam_size = beam_size
        self.cpu_threads = cpu_threads
        self.no_speech_threshold = no_speech_threshold
        self.hallucination_silence_threshold = hallucination_silence_threshold
        if compute_type == "auto":
            compute_type = auto_compute_type()
        self.compute_type = compute_type
        self.initial_prompt = load_initial_prompt() if initial_prompt is None else initial_prompt
        # hotwords z pola `hotwords` w commands.yaml (≤3 słowa); domyślnie "".
        self.hotwords = load_hotwords() if hotwords is None else hotwords
        self._model = None
        self._model_dir = model_dir

    def load(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        model_ref = self._resolve_model_ref()
        t0 = time.perf_counter()
        self._model = WhisperModel(
            model_ref,
            device="auto",
            compute_type=self.compute_type,
            cpu_threads=self.cpu_threads,
        )
        self.resolved_model_ref = str(model_ref)
        log.info(
            "ASR: faster-whisper %s (%s, %d wątków) załadowany w %.1f s; initial_prompt: %s",
            self.model_size,
            self.compute_type,
            self.cpu_threads,
            time.perf_counter() - t0,
            self.initial_prompt[:60] + ("…" if len(self.initial_prompt) > 60 else ""),
        )

    def _resolve_model_ref(self) -> str:
        """Woli lokalny model z manifestu (zweryfikowany SHA-256, R10).

        Kolejność: jawny model_dir → cache manifestu (`whisper-small`) →
        wbudowany fallback faster-whisper (pobiera z HF — tylko development)."""
        if self._model_dir is not None:
            return str(self._model_dir)
        from .manifest import load_manifest, verify_spec

        manifest_id = f"whisper-{self.model_size}"
        try:
            spec = load_manifest()[manifest_id]
            ok, msg = verify_spec(spec)
            if ok:
                from ..config.paths import models_dir

                return str(models_dir() / manifest_id)
            log.warning(
                "model %s w cache niezgodny z manifestem (%s) — fallback HF.", manifest_id, msg
            )
        except Exception as exc:
            log.warning("manifest niedostępny (%s) — fallback HF.", exc)
        return self.model_size

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def transcribe(self, audio: np.ndarray, language: str | None = None) -> ASRResult:
        """Transkrypcja mono float32 @ 16 kHz. Mierzy czas samego ASR."""
        self.load()
        arr = np.asarray(audio, dtype=np.float32)
        if arr.ndim > 1:
            arr = arr.mean(axis=1)
        t0 = time.perf_counter()
        segments, info = self._model.transcribe(  # type: ignore[union-attr]
            arr,
            language=language or self.language,
            beam_size=self.beam_size,
            temperature=0,
            initial_prompt=self.initial_prompt or None,
            hotwords=self.hotwords or None,
            condition_on_previous_text=False,
            word_timestamps=False,
            vad_filter=False,  # VAD robimy wcześniej, na strumieniu (Silero)
            no_speech_threshold=self.no_speech_threshold,
            hallucination_silence_threshold=self.hallucination_silence_threshold,
        )
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return ASRResult(
            text=text,
            elapsed_s=time.perf_counter() - t0,
            language=info.language,
            language_probability=info.language_probability,
            audio_seconds=info.duration,
        )


def transcribe_file(
    path: Path,
    engine: ASREngine | None = None,
    model_dir: Path | None = None,
    language: str = DEFAULT_LANGUAGE,
) -> ASRResult:
    """Transkrypcja pliku WAV/FLAC/MP3 (demo i eval). Dekodowanie: PyAV."""
    engine = engine or ASREngine(model_dir=model_dir, language=language)
    engine.load()
    from faster_whisper.audio import decode_audio

    audio = decode_audio(str(path), sampling_rate=SAMPLE_RATE)
    return engine.transcribe(np.asarray(audio, dtype=np.float32))
