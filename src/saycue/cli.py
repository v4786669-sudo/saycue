"""CLI SayCue (W1): pętla audio→ASR bez GUI.

python -m saycue                     # pętla na żywo (wake-word + PTT)
python -m saycue --file x.wav        # transkrypcja pliku (demo/eval)
python -m saycue --list-devices      # urządzenia audio
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="saycue",
        description="SayCue — offline'owy asystent głosowy dla streamerów (W1: audio→ASR).",
    )
    p.add_argument("--version", action="version", version=f"saycue {__version__}")
    p.add_argument("--file", type=Path, help="transkrypcja pliku WAV/FLAC/MP3 zamiast mikrofonu")
    p.add_argument("--list-devices", action="store_true", help="lista urządzeń audio i wyjście")
    p.add_argument(
        "--model",
        default="small",
        choices=["small", "medium", "tiny"],
        help="rozmiar modelu Whisper (domyślnie: small)",
    )
    p.add_argument("--language", default="pl", help="język ASR (domyślnie: pl)")
    p.add_argument(
        "--input",
        default="auto",
        choices=["auto", "wake", "ptt", "vad-gate"],
        help="wyzwalanie: auto=wake-word+PTT (domyślnie), wake, ptt, vad-gate",
    )
    p.add_argument("--device", type=int, default=None, help="indeks urządzenia sounddevice")
    p.add_argument("--alsa-device", default="default", help="urządzenie ALSA (fallback backend)")
    p.add_argument(
        "--end-silence", type=float, default=0.6, help="koniec mowy po N s ciszy (domyślnie: 0.6)"
    )
    p.add_argument(
        "--max-utterance",
        type=float,
        default=8.0,
        help="maks. długość wypowiedzi w s (domyślnie: 8)",
    )
    p.add_argument(
        "--debug-audio",
        type=Path,
        default=None,
        help="zapisuj wypowiedzi jako WAV do katalogu (debug)",
    )
    p.add_argument("--verbose", action="store_true", help="logowanie DEBUG")
    return p


def _cmd_list_devices() -> int:
    try:
        import sounddevice as sd

        print(sd.query_devices())
        print("\nDomyślne wejście:", sd.query_devices(kind="input").get("name", "?"))
        return 0
    except OSError as exc:
        print(f"sounddevice/PortAudio niedostępny ({exc}) — urządzenia ALSA:")
        from .audio._alsa_backend import list_devices

        for d in list_devices():
            print(f"  {d['alsa_name']:<16} {d['description']}")
        return 0


def _cmd_file(args) -> int:
    from .asr.whisper import ASREngine, transcribe_file

    engine = ASREngine(model_size=args.model, language=args.language)
    result = transcribe_file(args.file, engine=engine, language=args.language)
    print(f"plik : {args.file}")
    print(f'tekst: "{result.text}"')
    print(
        f"ASR  : {result.elapsed_s * 1000:.0f} ms | język {result.language} | "
        f"audio {result.audio_seconds:.2f} s | lang_prob {result.language_probability:.2f}"
    )
    return 0


def _cmd_live(args) -> int:
    from .asr.whisper import ASREngine
    from .audio.capture import AudioCapture
    from .pipeline import Pipeline
    from .vad.silero import SileroVAD
    from .wakeword.openwakeword import WakeWordDetector
    from .wakeword.ptt import PushToTalk

    use_wake = args.input in ("auto", "wake")
    use_ptt = args.input in ("auto", "ptt")
    use_vad_gate = args.input == "vad-gate"

    capture = AudioCapture(device=args.device, alsa_device=args.alsa_device)
    vad = SileroVAD()
    asr = ASREngine(model_size=args.model, language=args.language)
    wake = WakeWordDetector() if use_wake else None
    ptt = PushToTalk() if use_ptt else None
    if use_vad_gate:
        wake = ptt = None
    if wake is None and ptt is None and not use_vad_gate:
        logging.warning("brak trybu wyzwalania — używam VAD-gate (awaryjny tryb wejścia).")

    print(
        "SayCue W1 — pętla audio → ASR. Wyzwalanie: "
        + ("wake-word + PTT (Ctrl+Alt+Space)" if args.input == "auto" else args.input)
    )
    print(f"Powiedz komendę (maks. {args.max_utterance:.0f} s). Ctrl+C kończy.")

    pipeline = Pipeline(
        asr=asr,
        capture=capture,
        vad=vad,
        wake=wake,
        ptt=ptt,
        end_silence_s=args.end_silence,
        max_utterance_s=args.max_utterance,
        debug_audio_dir=args.debug_audio,
    )
    pipeline.run_forever()
    return 0


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    if args.list_devices:
        return _cmd_list_devices()
    if args.file:
        return _cmd_file(args)
    return _cmd_live(args)


if __name__ == "__main__":
    sys.exit(main())
