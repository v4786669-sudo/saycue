#!/usr/bin/env python3
"""Generuje nagrania testowe G1: piper TTS (pl_PL-gosia-medium) + szum pokoju.

Symulacja „realistycznego pokoju" (proxy dla W1):
- TTS piper (neuralny, damski głos PL) zamiast własnych nagrań,
- dodany szum otoczenia: brązowy szum + przydźwięk 50 Hz + kliknięcia klawiatury,
  SNR ~15 dB (typowe tło pokoju przy odległości 30–50 cm od mikrofonu),
- wyjście: 16 kHz mono float WAV (eval/recordings/<id>.wav).

Uwaga: prawdziwe nagrania ludzkie (3 akcenty) — tydzień 4, `eval/report.md`.
Wymaga: `piper-tts` (uv pip install piper-tts) i ffmpeg w PATH.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SAMPLE_RATE = 16000
DEFAULT_VOICE = "pl_PL-gosia-medium"


def ensure_piper_voice(voice: str) -> Path:
    """Pobiera głos piper do voices/ (HF hub), jeśli go nie ma."""
    voices_dir = ROOT / "voices"
    model = voices_dir / f"{voice}.onnx"  # piper.download_voices zapisuje płasko
    if model.is_file():
        return model
    print(f"pobieram głos piper: {voice} …")
    voices_dir.mkdir(exist_ok=True)
    r = subprocess.run(
        [sys.executable, "-m", "piper.download_voices", voice, "--data-dir", str(voices_dir)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 or not model.is_file():
        raise SystemExit(f"pobranie głosu nieudane: {r.stderr[-400:]}")
    return model


def synthesize(piper: str, voice_model: Path, text: str, out_wav: Path) -> None:
    """piper (22050 Hz) → ffmpeg → 16 kHz mono float32 WAV."""
    tmp = out_wav.with_suffix(".tmp.wav")
    r = subprocess.run(
        [piper, "--model", str(voice_model), "--output_file", str(tmp)],
        input=text + "\n",
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        raise SystemExit(f"piper błąd: {r.stderr[-400:]}")
    r = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(tmp),
            "-ar",
            str(SAMPLE_RATE),
            "-ac",
            "1",
            "-f",
            "f32le",
            str(out_wav.with_suffix(".f32")),
        ],
        capture_output=True,
    )
    if r.returncode != 0:
        raise SystemExit(f"ffmpeg błąd: {r.stderr[-400:]}")
    tmp.unlink(missing_ok=True)


def load_f32(path: Path) -> np.ndarray:
    return np.fromfile(path, dtype=np.float32)


def room_noise(n_samples: int, rng: np.random.Generator) -> np.ndarray:
    """Szum pokoju: brązowy szum + 50 Hz hum + klawiaturowe kliknięcia."""
    brown = np.cumsum(rng.standard_normal(n_samples))
    brown = brown / (np.abs(brown).max() + 1e-9)
    # łagodny dolnoprzepustowy (jednobiegunowy IIR) — „ściana" zamiast syku
    brown = np.convolve(brown, np.ones(48) / 48, mode="same")
    t = np.arange(n_samples) / SAMPLE_RATE
    hum = 0.05 * np.sin(2 * np.pi * 50 * t + 0.3)
    clicks = np.zeros(n_samples)
    for _ in range(4):
        pos = rng.integers(0, max(1, n_samples - 400))
        clicks[pos : pos + 400] += rng.uniform(0.3, 0.7) * np.exp(-np.arange(400) / 60)
    return 0.9 * brown + hum + 0.5 * clicks


def mix_speech_noise(speech: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    """Miesza mowę z szumem przy zadanym SNR (dB). Cisza przed/po mowie zostaje w tle."""
    speech_rms = np.sqrt(np.mean(np.square(speech)))
    noise_rms = np.sqrt(np.mean(np.square(noise))) + 1e-9
    gain = speech_rms / (noise_rms * 10 ** (snr_db / 20))
    return speech + gain * noise


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--commands",
        type=Path,
        default=ROOT / "eval" / "commands.yaml",
        help="plik z frazami (domyślnie eval/commands.yaml; G2: eval/g2_commands.yaml)",
    )
    ap.add_argument("--voice", default=DEFAULT_VOICE, help="głos piper (pl_PL-gosia-medium)")
    ap.add_argument("--snr-db", type=float, default=15.0, help="SNR szumu pokoju (domyślnie 15)")
    ap.add_argument("--pad-s", type=float, default=0.35, help="cisza przed/po mowie (s)")
    ap.add_argument("--out", type=Path, default=ROOT / "eval" / "recordings")
    args = ap.parse_args()

    piper = shutil.which("piper") or str(Path(sys.executable).parent / "piper")
    if piper is None:
        raise SystemExit("brak piper w PATH (uv pip install piper-tts)")
    voice_model = ensure_piper_voice(args.voice)

    commands = yaml.safe_load(args.commands.read_text(encoding="utf-8"))
    phrases = commands["phrases"]
    args.out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)

    print(
        f"generuję {len(phrases)} nagrań z {args.commands.name} (SNR {args.snr_db} dB, pad {args.pad_s} s)…"
    )
    for entry in phrases:
        pid, phrase = entry["id"], entry["phrase"]
        # G2: tylko frazy z własnym wav (g1_XX są współdzielone z G1)
        wav_name = entry.get("wav", f"{pid}.wav")
        if wav_name.startswith("g1_"):
            print(f"  {wav_name}: współdzielone z G1 — pomijam")
            continue
        wav = args.out / wav_name
        synthesize(piper, voice_model, phrase, wav)
        speech = load_f32(wav.with_suffix(".f32"))
        wav.with_suffix(".f32").unlink(missing_ok=True)
        pad = int(args.pad_s * SAMPLE_RATE)
        noise = room_noise(len(speech) + 2 * pad, rng)
        padded = np.concatenate([np.zeros(pad), speech, np.zeros(pad)])
        mixed = mix_speech_noise(padded, noise, args.snr_db)
        mixed = np.clip(mixed, -1.0, 1.0)
        pcm = (mixed * 32767).astype(np.int16)
        import wave

        with wave.open(str(wav), "wb") as f:
            f.setnchannels(1)
            f.setsampwidth(2)
            f.setframerate(SAMPLE_RATE)
            f.writeframes(pcm.tobytes())
        print(f"  {wav.name}: {len(speech) / SAMPLE_RATE:.2f} s mowy, '{phrase}'")

    print(f"\nNagrania w: {args.out}")
    print("Uwaga: proxy TTS+szum — prawdziwe głosy testujemy w W4 (3 akcenty).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
