"""Wake-word: openWakeWord (Apache-2.0) + cooldown 500 ms.

Domyślne słowo: „hej asystent" (PL) — model EN `alexa_v0.1` jako proxy
fonetyczny do czasu wytrenowania własnego modelu PL (ryzyko R6, architektura
§3.1). Fallback niezawodny: push-to-talk (hotkey) — patrz `ptt.py`.

Cooldown 500 ms: jedno wybudzenie nie uruchamia dwóch sesji.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np

from ..asr.manifest import load_manifest
from ..config.paths import models_dir

DEFAULT_MODEL = "alexa_v0.1"
THRESHOLD = 0.5
COOLDOWN_S = 0.5
# openWakeWord wymaga chunków ≥ 80 ms; zbieramy 3 ramki po 512 próbek (96 ms)
PREDICT_CHUNK = 512 * 3

log = logging.getLogger(__name__)


class WakeWordDetector:
    """Detekcja wybudzenia na strumieniu 16 kHz mono float32."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        threshold: float = THRESHOLD,
        cooldown_s: float = COOLDOWN_S,
        model_dir: Path | None = None,
    ):
        self.model_name = model_name
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self._last_trigger = -cooldown_s
        self._pending = np.zeros(0, dtype=np.float32)
        self._model = None
        # układ katalogów zgodny z manifestem: <cache>/models/openwakeword-alexa/
        self._model_dir = model_dir or models_dir() / "openwakeword-alexa"

    def load(self) -> None:
        if self._model is not None:
            return
        model_file = self._model_dir / f"{self.model_name}.onnx"
        if not model_file.is_file():
            raise FileNotFoundError(
                f"model wake-word {self.model_name}.onnx nie znaleziony w {self._model_dir}. "
                "Uruchom: python scripts/download_models.py"
            )
        import openwakeword

        # modele cech (melspectrogram + embedding) też z cache manifestu (R10),
        # nie z katalogu pakietu — openwakeword.Model przekazuje kwargs dalej
        self._model = openwakeword.Model(
            wakeword_models=[str(model_file)],
            inference_framework="onnx",
            melspec_model_path=str(self._model_dir / "melspectrogram.onnx"),
            embedding_model_path=str(self._model_dir / "embedding_model.onnx"),
        )
        log.info(
            "wake-word: %s załadowany (próg %.2f, cooldown %.0f ms)",
            self.model_name,
            self.threshold,
            self.cooldown_s * 1000,
        )

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def feed(self, chunk: np.ndarray) -> bool:
        """Zwraca True, gdy wykryto wybudzenie (z cooldownem)."""
        if self._model is None:
            return False
        self._pending = np.concatenate([self._pending, np.asarray(chunk, dtype=np.float32)])
        if self._pending.size < PREDICT_CHUNK:
            return False
        window, self._pending = self._pending[:PREDICT_CHUNK], self._pending[PREDICT_CHUNK:]
        try:
            scores = self._model.predict(window)
        except Exception:
            log.exception("wake-word: predict nieudany")
            return False
        score = max(scores.values())
        now = time.monotonic()
        if score >= self.threshold and (now - self._last_trigger) >= self.cooldown_s:
            self._last_trigger = now
            log.info("wake-word: wybudzenie (score=%.3f)", score)
            return True
        return False


def wakeword_model_path(model_name: str = DEFAULT_MODEL) -> Path:
    spec = load_manifest()["openwakeword-alexa"]
    return models_dir() / spec.id / f"{model_name}.onnx"
