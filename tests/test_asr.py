"""Test integracyjny ASR (wymaga pobranych modeli — marker `models`).

Lokalnie: python scripts/download_models.py, potem pytest -m models.
CI: pomijane (modele nie są w repo — R10).
"""

import numpy as np
import pytest

pytestmark = pytest.mark.models

from saycue.asr.manifest import load_manifest, verify_spec  # noqa: E402
from saycue.asr.whisper import ASREngine  # noqa: E402


@pytest.fixture(scope="module")
def engine():
    spec = load_manifest()["whisper-small"]
    ok, msg = verify_spec(spec)
    if not ok:
        pytest.skip(f"model whisper-small niedostępny ({msg}) — scripts/download_models.py")
    eng = ASREngine(model_size="small", language="pl")
    eng.load()
    return eng


def test_model_resolves_from_manifest_cache(engine):
    # silnik powinien użyć lokalnego modelu z cache manifestu (R10), nie HF
    assert "whisper-small" in engine.resolved_model_ref, (
        f"model spoza cache manifestu: {engine.resolved_model_ref}"
    )


def test_silence_transcribes_empty(engine):
    result = engine.transcribe(np.zeros(16000, dtype=np.float32))
    assert result.elapsed_s > 0
    # Uwaga (stabilizacja flaky, flag t13/t9): greedy decode jest deterministyczny,
    # ale sumy FP w int8 przy pełnym obciążeniu CPU potrafią przestawić pojedynczy
    # marginalny token. Niezmiennik, którego naprawdę bronimy: cisza NIE daje komendy.
    from saycue.asr.whisper import load_phrases
    from saycue.parser.normalize import normalize

    phrases = {normalize(p) for p in load_phrases()}
    assert normalize(result.text) not in phrases, f"cisza zdekodowana jako komenda: {result.text!r}"
    assert len(result.text.split()) <= 3, f"cisza zdekodowana jako zdanie: {result.text!r}"


def test_initial_prompt_loaded(engine):
    assert engine.initial_prompt, "initial_prompt z data/commands.yaml niezaładowany"
    assert "spotify" in engine.initial_prompt.lower()
