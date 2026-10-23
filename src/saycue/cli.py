"""CLI SayCue (W2): pętla audio → ASR → parser → akcje (bez GUI).

python -m saycue                     # pętla na żywo (wake-word + PTT), akcje dry-run
python -m saycue --live              # jak wyżej, ale akcje NAPRAWDĘ wykonują się w systemie
python -m saycue --file x.wav        # demo end-to-end: plik → transkrypcja → intencja → akcja
python -m saycue --list-devices      # urządzenia audio

Bezpieczeństwo: domyślnie `--dry-run` (akcje tylko planowane, nic nie dotyka
systemu). `--live` włącza realne wykonanie (xdotool/pactl/gio/OBS).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import __version__

DEFAULT_PRESETS = ["obs-core", "apps-open", "apps-streaming", "elite-dangerous"]


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="saycue",
        description="SayCue — offline'owy asystent głosowy dla streamerów (W3: audio→ASR→akcje + doctor + presety).",
    )
    p.add_argument("--version", action="version", version=f"saycue {__version__}")
    sub = p.add_subparsers(dest="command")

    # saycue doctor [--json] [--faq] [--obs URL] [--mic-time N]
    dp = sub.add_parser(
        "doctor", help="self-diagnostyka: mikrofon, OBS, modele, FP/h, offline (kody 0/1/2)"
    )
    dp.add_argument("--json", action="store_true", help="wynik maszynowo-czytelny")
    dp.add_argument("--faq", action="store_true", help="wygeneruj docs/faq.md i zakończ")
    dp.add_argument("--obs", default="", help="OBS WebSocket URL (host:port[:hasło])")
    dp.add_argument("--mic-time", type=float, default=2.0, help="czas pomiaru mikrofonu (s)")

    # saycue gui [--no-tray] [--offscreen]
    gp = sub.add_parser("gui", help="GUI + tray (W3); --offscreen dla testów")
    gp.add_argument("--no-tray", action="store_true", help="bez ikony w trayu")
    gp.add_argument("--offscreen", action="store_true", help="platforma offscreen (testy/CI)")

    # saycue presets validate [path...] [--json]
    pp = sub.add_parser("presets", help="presety YAML (§2.5): walidacja JSON Schema + reguły S2–S6")
    pp.add_argument("--validate", action="store_true", dest="validate", help="waliduj presets/")
    pp.add_argument("paths", nargs="*", help="katalogi presetów (domyślnie: wszystkie)")
    pp.add_argument("--json", action="store_true", help="wynik maszynowo-czytelny")
    p.add_argument("--file", type=Path, help="demo end-to-end z pliku WAV/FLAC/MP3")
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
        "--presets",
        default=",".join(DEFAULT_PRESETS),
        help="aktywne presety (przecinkami; domyślnie: obs-core,apps-open,apps-streaming,elite-dangerous)",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="realne wykonanie akcji (domyślnie: dry-run — tylko plan akcji)",
    )
    p.add_argument(
        "--obs", default=None, help="OBS WebSocket URL (host:port[:hasło]) — np. 127.0.0.1:4455"
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


def _build_components(args):
    """Parser + rejestr akcji + kontekst (wspólne dla live i file)."""
    from .actions import ActionContext, build_default_registry
    from .parser import IntentParser

    parser = IntentParser(active_presets=args.presets.split(","))
    registry = build_default_registry()
    ctx = ActionContext(apps=parser.config.apps, obs=None, dry_run=not args.live)
    if args.obs:
        from .actions.obs import ObsClient, ObsError

        parts = args.obs.split(":")
        host, port = parts[0], int(parts[1]) if len(parts) > 1 else 4455
        password = parts[2] if len(parts) > 2 else ""
        obs = ObsClient(host=host, port=port, password=password)
        try:
            obs.connect()
        except ObsError as exc:
            print(f"OBS niedostępny ({exc}) — akcje obs.* będą zwracać obs_not_connected.")
        else:
            ctx.obs = obs
            print(f"OBS: połączono z {host}:{port}")
    return parser, registry, ctx


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
    parser, registry, ctx = _build_components(args)
    parsed = parser.parse(result.text)
    if parsed is None:
        cand = ", ".join(c.phrase for c in parser.candidates(result.text, 3)) or "—"
        print(f"intencja: BRAK — czy chodziło ci o: {cand}")
        return 1
    action_result = registry.execute(parsed.intent, parsed.slots, ctx)
    print(f"intencja: {parsed.intent} {dict(parsed.slots)} [{parsed.source}/{parsed.origin}]")
    print(
        f"akcja  : {'✓ ' + action_result.message if action_result.ok else '✗ ' + (action_result.message or action_result.error)}"
    )
    return 0 if action_result.ok else 1


def _cmd_live(args) -> int:
    from .asr.whisper import ASREngine
    from .audio.capture import AudioCapture
    from .orchestrator import Orchestrator
    from .vad.silero import SileroVAD
    from .wakeword.openwakeword import WakeWordDetector
    from .wakeword.ptt import PushToTalk

    use_wake = args.input in ("auto", "wake")
    use_ptt = args.input in ("auto", "ptt")
    use_vad_gate = args.input == "vad-gate"

    capture = AudioCapture(device=args.device, alsa_device=args.alsa_device)
    vad = SileroVAD()
    asr = ASREngine(model_size=args.model, language=args.language)
    parser, registry, ctx = _build_components(args)
    wake = WakeWordDetector() if use_wake else None
    ptt = PushToTalk() if use_ptt else None
    if use_vad_gate:
        wake = ptt = None
    if wake is None and ptt is None and not use_vad_gate:
        logging.warning("brak trybu wyzwalania — używam VAD-gate (awaryjny tryb wejścia).")

    mode = "DRY-RUN (plan akcji)" if ctx.dry_run else "LIVE (realne akcje)"
    print(
        f"SayCue W2 — audio → ASR → parser → akcje. Tryb: {mode} | wyzwalanie: "
        + ("wake-word + PTT (Ctrl+Alt+Space)" if args.input == "auto" else args.input)
        + f" | presety: {args.presets}"
    )
    print(f"Powiedz komendę (maks. {args.max_utterance:.0f} s). Ctrl+C kończy.")

    orchestrator = Orchestrator(
        asr=asr,
        capture=capture,
        vad=vad,
        wake=wake,
        ptt=ptt,
        parser=parser,
        registry=registry,
        ctx=ctx,
        end_silence_s=args.end_silence,
        max_utterance_s=args.max_utterance,
        debug_audio_dir=args.debug_audio,
    )
    orchestrator.run_forever()
    return 0


def _cmd_doctor(args) -> int:
    from .doctor import format_checks, generate_faq, run_checks, verdict

    if args.faq:
        faq_path = Path(__file__).resolve().parents[2] / "docs" / "faq.md"
        faq_path.parent.mkdir(parents=True, exist_ok=True)
        faq_path.write_text(generate_faq(), encoding="utf-8")
        print(f"FAQ wygenerowane: {faq_path}")
        return 0
    checks, duration = run_checks(obs_url=args.obs, mic_s=args.mic_time)
    code, summary = verdict(checks)
    if args.json:
        import json

        print(
            json.dumps(
                {
                    "ok": code == 0,
                    "exit_code": code,
                    "summary": summary,
                    "duration_s": round(duration, 2),
                    "errors": len([c for c in checks if c.status == "error"]),
                    "warnings": len([c for c in checks if c.status == "warn"]),
                    "checks": [
                        {"name": c.name, "status": c.status, "message": c.message, "fix": c.fix}
                        for c in checks
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"saycue doctor — {summary} ({duration:.1f} s)")
        print(format_checks(checks))
    return code


def _cmd_presets(args) -> int:
    import subprocess
    import sys as _sys

    script = Path(__file__).resolve().parents[2] / "presets" / "validate.py"
    if script.is_file():
        cmd = [_sys.executable, str(script)]
        if args.json:
            cmd.append("--json")
        cmd.extend(args.paths)
        return subprocess.call(cmd)
    # B-05: instalacja (bundle) bez skryptu dev — walidacja schematu przez loader
    from .config.paths import presets_dir
    from .parser.presets import PresetError, PresetLoader

    loader = PresetLoader(presets_dir(), validate=True)
    errors: list[str] = []
    for preset_id in sorted(loader.list_available()):
        try:
            loader.load(preset_id)
            print(f"✓ {preset_id}")
        except (PresetError, ValueError) as exc:
            errors.append(f"{preset_id}: {exc}")
            print(f"✗ {preset_id}: {exc}")
    if errors:
        print(
            f"{len(errors)} preset(ów) z błędami (pełna walidacja: tryb dev — "
            "repozytorium, `python presets/validate.py`)."
        )
        return 1
    print(f"OK — {len(loader.list_available())} presetów zgodnych ze schematem.")
    return 0


def main(argv=None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    if args.command == "doctor":
        return _cmd_doctor(args)
    if args.command == "gui":
        from .ui.app import run_gui

        return run_gui(no_tray=args.no_tray, offscreen=args.offscreen)
    if args.command == "presets":
        return _cmd_presets(args)
    if args.list_devices:
        return _cmd_list_devices()
    if args.file:
        return _cmd_file(args)
    return _cmd_live(args)


if __name__ == "__main__":
    sys.exit(main())
