"""Zbiór regresyjny: tekst → intent (≥40 par), aktywacja:
rdzeń (data/commands.yaml) + presety obs-core + apps-open + apps-streaming.

Reguły weryfikowane na żywych danych:
* dłuższa fraza wygrywa („wycisz mikrofon" > „wycisz", „cisza w kompie" → głośniki);
* gołe „wycisz" → mikrofon (obs.mute), NIE głośniki (decyzja t13/kapitan);
* przy identycznej frazie wygrywa później aktywowany preset (slot → preset);
* szablony {target}/{scene} rozwiązują slot po apps.yaml + presetach;
* fuzzy ≥ 0.78 (typy, przekręcenia), poniżej → brak intencji.
"""

from __future__ import annotations

import pytest

# (tekst, intent | None, slots | None)
CASES = [
    # ------------------------------ app.open (rdzeń + apps-open + szablony)
    ("Otwórz Spotify!", "app.open", {"target": "spotify"}),
    ("otworz spotify", "app.open", {"target": "spotify"}),
    ("spotify", "app.open", {"target": "spotify"}),
    ("Włącz Discord", "app.open", {"target": "discord"}),
    ("discord", "app.open", {"target": "discord"}),
    ("obs", "app.open", {"target": "obs"}),
    ("włącz obs", "app.open", {"target": "obs"}),
    ("otwórz przeglądarkę", "app.open", {"target": "browser"}),
    ("otwórz notatnik", "app.open", {"target": "notepad"}),
    ("otwórz czat gpt", "app.open", {"target": "chatgpt"}),
    ("otwórz pliki", "app.open", {"target": "explorer"}),
    ("otwórz mikser", "app.open", {"target": "mixer"}),
    ("otwórz steam", "app.open", {"target": "steam"}),
    ("kalkulator", "app.open", {"target": "kalkulator"}),
    ("otwórz blender", "app.open", {"target": "blender"}),  # szablon + apps.yaml
    ("odpal dc", "app.open", {"target": "discord"}),  # szablon + alias z rdzenia
    ("uruchom obs studio", "app.open", {"target": "obs"}),  # szablon + alias presetu
    # ------------------------------ app.close (apps-open)
    ("zamknij spotify", "app.close", {"target": "spotify"}),
    ("wyłącz obs", "app.close", {"target": "obs"}),
    ("zamknij przeglądarkę", "app.close", {"target": "browser"}),
    ("zamknij discord", "app.close", {"target": "discord"}),
    # ------------------------------ obs.scene (obs-core + szablony)
    ("scena live", "obs.scene", {"scene": "Live"}),
    ("scena gameplay", "obs.scene", {"scene": "Gameplay"}),
    ("scena pvp", "obs.scene", {"scene": "PVP"}),
    ("przełącz na pvp", "obs.scene", {"scene": "PVP"}),
    ("pvp", "obs.scene", {"scene": "PVP"}),
    ("scena startowa", "obs.scene", {"scene": "Starting Soon"}),
    ("starting soon", "obs.scene", {"scene": "Starting Soon"}),
    ("przerwa", "obs.scene", {"scene": "BRB"}),
    ("wracam za chwilę", "obs.scene", {"scene": "BRB"}),
    ("kończymy stream", "obs.scene", {"scene": "Ending"}),
    ("następna scena", "obs.scene", {"scene": "__next__"}),
    ("poprzednia", "obs.scene", {"scene": "__prev__"}),
    ("scena brb", "obs.scene", {"scene": "BRB"}),  # szablon → słownik scen
    ("scena stream", "obs.scene", {"scene": "stream"}),  # szablon, brak w słowniku
    ("scena pvn", "obs.scene", {"scene": "pvn"}),  # poniżej progu fuzzy słownika
    # ------------------------------ obs.mute (rdzeń + obs-core)
    ("cisza", "obs.mute", {"source": "mic", "state": "toggle"}),
    ("wycisz", "obs.mute", {"source": "mic", "state": "toggle"}),  # gołe: mikrofon!
    ("wycisz mikrofon", "obs.mute", {"source": "Mic/Aux", "state": "on"}),
    ("wycisz mic", "obs.mute", {"source": "Mic/Aux", "state": "on"}),
    ("mute", "obs.mute", {"source": "Mic/Aux", "state": "toggle"}),
    ("odcisz mikrofon", "obs.mute", {"source": "Mic/Aux", "state": "off"}),
    ("włącz mikrofon", "obs.mute", {"source": "Mic/Aux", "state": "off"}),
    ("przełącz mikrofon", "obs.mute", {"source": "Mic/Aux", "state": "toggle"}),
    ("wycisz dźwięk pulpitu", "obs.mute", {"source": "Desktop Audio", "state": "on"}),
    # ------------------------------ obs.record
    ("nagrywaj", "obs.record", {"state": "start"}),
    ("zacznij nagrywać", "obs.record", {"state": "start"}),
    ("start nagrywania", "obs.record", {"state": "start"}),
    ("rozpocznij nagrywanie", "obs.record", {"state": "start"}),
    ("stop nagrywania", "obs.record", {"state": "stop"}),
    ("przestań nagrywać", "obs.record", {"state": "stop"}),
    ("koniec nagrywania", "obs.record", {"state": "stop"}),
    # ------------------------------ obs.replay
    ("replay", "obs.replay", {"action": "save"}),
    ("zapisz replay", "obs.replay", {"action": "save"}),
    ("zapisz powtórkę", "obs.replay", {"action": "save"}),
    ("włącz replay buffer", "obs.replay", {"action": "start"}),
    # ------------------------------ obs.source_toggle
    ("wycisz powiadomienia", "obs.source_toggle", {"source": "Alerts", "state": "toggle"}),
    # ------------------------------ system.volume (rdzeń + apps-streaming)
    ("głośniej", "system.volume", {"direction": "up", "step": 2}),
    ("podgłośnij", "system.volume", {"direction": "up", "step": 2}),
    ("ciszej", "system.volume", {"direction": "down", "step": 2}),
    ("cisza w kompie", "system.volume", {"direction": "down", "step": 30}),
    ("wycisz system", "system.volume", {"direction": "down", "step": 30}),
    ("ścisz", "system.volume", {"delta": -20}),
    ("cichutko", "system.volume", {"delta": -20}),
    ("zwiększ głośność", "system.volume", {"delta": 20}),
    # ------------------------------ input.keys (rdzeń)
    ("dasz", "input.keys", {"keys": ["shift", "space"]}),
    ("dash", "input.keys", {"keys": ["shift", "space"]}),
    ("shift dash", "input.keys", {"keys": ["shift", "space"]}),
    ("uniki", "input.keys", {"keys": ["shift", "space"]}),
    # ------------------------------ window.focus (apps-streaming)
    ("przełącz na panel", "window.focus", {"target": "streamdeck"}),
    # ------------------------------ wypełniacze (krok 3 §2.3)
    ("hej, proszę otwórz spotify", "app.open", {"target": "spotify"}),
    ("ok asystent, nagrywaj", "obs.record", {"state": "start"}),
    ("proszę głośniej", "system.volume", {"direction": "up", "step": 2}),
    # ------------------------------ fuzzy ≥ 0.78
    ("otworz spotifaj", "app.open", {"target": "spotify"}),
    ("wlancz discord", "app.open", {"target": "discord"}),
    ("ciszejj", "system.volume", {"direction": "down", "step": 2}),
    ("nagrywa", "obs.record", {"state": "start"}),
    # ------------------------------ negatywne (None)
    ("zrób mi kawę", None, None),
    ("dusz", None, None),  # 0.75 < próg
    ("zupełny bełkot", None, None),
    ("włącz", None, None),  # sam szablon bez wartości slotu
    ("elite podwozie", None, None),  # gra nieaktywna w tej aktywacji
]


@pytest.mark.parametrize("text,intent,slots", CASES, ids=[c[0] for c in CASES])
def test_text_to_intent(intent_parser, text, intent, slots):
    result = intent_parser.parse(text)
    if intent is None:
        assert result is None, f"{text!r} → {result}"
        return
    assert result is not None, f"{text!r} nie dopasowano"
    assert result.intent == intent, f"{text!r}: {result.intent} != {intent}"
    assert dict(result.slots) == slots, f"{text!r}: sloty {dict(result.slots)} != {slots}"
    assert result.score >= 0.78
    assert result.matched


def test_pair_count_is_at_least_40():
    positive = [c for c in CASES if c[1] is not None]
    assert len(CASES) >= 40
    assert len(positive) >= 40
