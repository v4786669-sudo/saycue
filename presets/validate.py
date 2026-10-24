"""SayCue — walidator presetów YAML.

Bez zależności poza PyYAML + jsonschema (są w pyproject jako zależności konfiguracji).

Użycie:
    python3 presets/validate.py                # waliduje wszystkie katalogi w presets/
    python3 presets/validate.py presets/obs-core  # jeden preset
    python3 presets/validate.py --json         # wynik maszynowo-czytelny (CI)

Reguły (poziom błąd = exit 1):
  S1  zgodność z presets/schema.json
  S2  id presetu == nazwa katalogu
  S3  brak plików wykonywalnych (.py/.sh/.exe/.dll/.bat/.ps1) w katalogu presetu
  S4  3–6 fraz na komendę, każda fraza unikalna w CAŁYM katalogu presets/
  S5  ≥5 fraz na liście phrases (initial_prompt)
  S6  sloty zgodne z intencją (SLOT_RULES)
Reguły (poziom ostrzeżenie):
  W1  brak jakiejkolwiek frazy PL w komendzie (preset musi działać po polsku)
  W2  kolizja podciągów między różnymi intencjami (wygrywa dłuższa — §2.3)
  W3  preset nie ma `requires.obs` mimo intencji obs.*
Exit: 0 = OK, 1 = błędy.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
    from jsonschema import Draft202012Validator
except ImportError:  # pragma: no cover
    sys.exit("Brak zależności: pip install pyyaml jsonschema")

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "schema.json"
FORBIDDEN_SUFFIXES = {".py", ".sh", ".exe", ".dll", ".bat", ".ps1", ".cmd", ".js"}
PL_CHARS = set("ąćęłńóśźż")
# Typowe polskie słowa komend (bez diakrytyków) — do heurystyki W1.
PL_WORDS = {
    "wlacz", "wylacz", "otworz", "zamknij", "przelacz", "wycisz", "odcisz", "pokaz",
    "nastepna", "poprzednia", "scena", "szesc", "sciezka", "siedem", "przepustnica",
    "naprzod", "wstecz", "gore", "dol", "lewo", "prawo", "zapisz", "wczytaj", "start",
    "gaz", "zero", "pelen", "maks", "maksymalna", "procent", "statek", "dokowanie",
    "bron", "bronie", "cel", "wrogi", "mapa", "plan", "lot", "przerwa", "koniec",
    "hamuj", "skanuj", "przyspiesz", "skok", "lat", "leć", "spowalniacze",
}


def normalize(text: str) -> str:
    """Ta sama normalizacja co parser (§2.3): lowercase, fold diakrytyków, bez interpunkcji."""
    text = text.lower().strip()
    table = str.maketrans("ąćęłńóśźż", "acelnoszz")
    text = text.translate(table)
    return re.sub(r"[^\w\s]", "", text).strip()


SLOT_RULES: dict[str, dict[str, set[str]]] = {
    "app.open": {"required": {"target"}, "allowed": {"target"}},
    "app.close": {"required": {"target"}, "allowed": {"target"}},
    "input.keys": {"required": set(), "allowed": {"keys", "keybind"}},
    "system.volume": {"required": {"direction"}, "allowed": {"direction", "step"}},
    "obs.scene": {"required": {"scene"}, "allowed": {"scene"}},
    "obs.mute": {"required": {"source"}, "allowed": {"source", "state"}},
    "obs.source_toggle": {"required": {"source"}, "allowed": {"source", "state"}},
    "obs.record": {"required": set(), "allowed": {"action"}},
    "obs.replay": {"required": set(), "allowed": {"buffer"}},
    "window.focus": {"required": {"target"}, "allowed": {"target"}},
}


class Report:
    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []      # (preset, message)
        self.warnings: list[tuple[str, str]] = []

    def err(self, preset: str, msg: str) -> None:
        self.errors.append((preset, msg))

    def warn(self, preset: str, msg: str) -> None:
        self.warnings.append((preset, msg))

    @property
    def ok(self) -> bool:
        return not self.errors


def is_polish(phrase: str) -> bool:
    """Heurystyka: diakrytyki PL albo słowo z listy typowych polskich słów komend."""
    if set(phrase) & PL_CHARS:
        return True
    words = set(normalize(phrase).split())
    return bool(words & PL_WORDS)


# Presety gry są wyłącznie wzajemnododatkowe: aktywny jest preset jednej gry naraz (GUI wybiera grę),
# więc kolizje fraz liczymy w obrębie kłtku gry. OBS i aplikacje są uniwersalne → zawsze aktywne.
COLLISION_NAMESPACES = {"obs-core": "universal", "apps-open": "universal", "apps-streaming": "universal"}
# Prefiksy rozdzielające gry przy jednej aktywnej grze (presety gier dzielą gramatykę §2.3).
GAME_PREFIXES = {"elite", "star", "lot", "dcs", "mine"}


def collision_ns(name: str) -> str:
    return COLLISION_NAMESPACES.get(name, "game")


def validate_preset(path: Path, validator: Draft202012Validator, rep: Report, seen: list[dict[str, Any]]) -> None:
    name = path.name
    files = [p for p in path.rglob("*") if p.is_file()]
    for f in files:
        rel = f.relative_to(path)
        try:
            shown = str(f.relative_to(ROOT))
        except ValueError:
            shown = str(rel)
        if f.suffix.lower() in FORBIDDEN_SUFFIXES:
            rep.err(name, f"S3 preset nie może zawierać kodu: {shown}")
        elif f.name not in {"preset.yaml", "README.md", "LICENSE"}:
            rep.err(name, f"S3 nieoczekiwany plik w katalogu presetu: {shown}")

    yaml_path = path / "preset.yaml"
    if not yaml_path.exists():
        rep.err(name, "S1 brak pliku preset.yaml")
        return

    try:
        data: Any = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        rep.err(name, f"S1 invalid YAML: {exc}")
        return
    if not isinstance(data, dict):
        rep.err(name, "S1 preset.yaml musi być mapą (object)")
        return

    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        for e in errors[:12]:
            where = "/".join(map(str, e.absolute_path)) or "<root>"
            rep.err(name, f"S1 schema: {where}: {e.message}")
        return

    if data["id"] != name:
        rep.err(name, f"S2 id={data['id']!r} nie równa się nazwie katalogu {name!r}")

    phrases_global: list[str] = list(data.get("phrases", []))
    intents = set()
    for cmd in data["commands"]:
        intents.add(cmd["intent"])
        cid = cmd["id"]
        cphrases = cmd["phrases"]

        # S4 — 3–6 fraz (schema) + unikalność w całym katalogu
        if not 3 <= len(cphrases) <= 6:
            rep.err(name, f"S4 {cid}: {len(cphrases)} fraz (wymagane 3–6)")
        norm = [normalize(p) for p in cphrases]
        if len(set(norm)) != len(norm):
            rep.err(name, f"S4 {cid}: powtarzające się frazy po normalizacji")
        for p, np_ in zip(cphrases, norm):
            ns = collision_ns(name)
            dup = next((e for e in seen if e["phrase"] == np_ and e["ns"] == ns), None)
            if dup:
                rep.err(name, f"S4 kolizja frazy {p!r} z presetem {dup['preset']!r} (ta sama aktywacja)")
            seen.append({"phrase": np_, "preset": name, "ns": ns})

        # W1 — PL przed EN (heurystyka: pierwsza fraza ma diakrytyki / latynizm PL)
        # S6 — sloty zgodne z intencją
        rule = SLOT_RULES[cmd["intent"]]
        slots = cmd.get("slots", {}) or {}
        missing = rule["required"] - set(slots)
        extra = set(slots) - rule["allowed"]
        if missing:
            rep.err(name, f"S6 {cid}: brak slotu {sorted(missing)} dla intent {cmd['intent']}")
        if extra:
            rep.err(name, f"S6 {cid}: sloty niepasujące do intent: {sorted(extra)}")

        # sloty keys/keybind wzajemnie się wykluczają
        if {"keys", "keybind"} <= set(slots):
            rep.err(name, f"S6 {cid}: podaj albo keys, albo keybind (nie oba)")

        # W1 — komenda musi mieć choć jedną frazę PL (diakrytyki albo PL_WORDS)
        if not any(is_polish(p) for p in cphrases):
            rep.warn(name, f"W1 {cid}: brak frazy PL - preset powinien działać po polsku")

        # W: target musi być zmapowany w apps[]
        target = slots.get("target")
        if target:
            apps = {a["id"] for a in data.get("apps", [])} | {
                a.get("id") for a in data.get("apps", [])
            }
            if target not in apps:
                rep.warn(name, f"W4 {cid}: target {target!r} nie zdefiniowany w apps[]")

    # S5 — phrases dla initial_prompt
    if len(phrases_global) < 5:
        rep.err(name, f"S5 phrases: {len(phrases_global)} fraz (wymagane ≥5)")

    # W3 — preset z intencjami obs.* powinien deklarować requires.obs
    if any(i.startswith("obs.") for i in intents) and not data.get("requires", {}).get("obs"):
        rep.warn(name, "W3 używa intencji obs.*, ale nie deklaruje requires.obs: true")


def check_substring_collisions(presets: dict[str, dict[str, Any]], rep: Report) -> None:
    """W2: fraza A jest podciągiem frazy B z inną intencją → dopuszczalne, ale zgłoś."""
    entries: list[tuple[str, str, str, str, str]] = []  # preset, cid, intent, phrase, norm
    for pname, data in presets.items():
        for cmd in data.get("commands", []):
            for p in cmd.get("phrases", []):
                entries.append((pname, cmd["id"], cmd["intent"], p, normalize(p)))
    for i, (pa, ca, ia, phr_a, na) in enumerate(entries):
        for pb, cb, ib, phr_b, nb in entries[i + 1 :]:
            if ia == ib:
                continue
            if na == nb:
                continue  # duplikaty łapie S4
            if not (na in nb or nb in na) or len(na.split()) == len(nb.split()):
                continue
            longer, longer_phrase, longer_preset = (na, phr_a, pa) if len(na) > len(nb) else (nb, phr_b, pb)
            # uzasadniona kolizja: dłuższa fraza ma prefiks gry (np. "star podwozie"), która
            # rozdziela przestrzenie nazw przy aktywacji presetu gry (§2.3 + GAME_PREFIXES)
            if longer.split()[0] in GAME_PREFIXES:
                continue
            rep.warn(
                pa if len(na) < len(nb) else pb,
                f"W2 kolizja podciągów: {phr_a!r} ({ia}) ⊂ {phr_b!r} ({ib}) - wygrywa dłuższa fraza (§2.3)",
            )


def run(targets: list[Path], as_json: bool = False) -> int:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    rep = Report()
    seen: list[dict[str, Any]] = []
    loaded: dict[str, dict[str, Any]] = {}

    dirs = [p for p in targets if p.is_dir() and (p / "preset.yaml").exists()]
    if not dirs:
        print("Brak presetów do walidacji.", file=sys.stderr)
        return 2

    for d in sorted(dirs):
        validate_preset(d, validator, rep, seen)
        try:
            loaded[d.name] = yaml.safe_load((d / "preset.yaml").read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            loaded[d.name] = {}

    check_substring_collisions(loaded, rep)

    if "--index" in sys.argv:
        index = {}
        for pname, data in sorted(loaded.items()):
            index[pname] = {
                "name": data.get("name"),
                "version": data.get("version"),
                "kind": data.get("kind"),
                "platforms": data.get("platforms", []),
                "game": data.get("game"),
                "commands": len(data.get("commands", [])),
                "phrases": sum(len(c.get("phrases", [])) for c in data.get("commands", [])),
            }
        (ROOT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Zapisano index.json ({len(index)} presetów)")

    if as_json:
        print(json.dumps({
            "presets": sorted(loaded),
            "errors": [{"preset": p, "message": m} for p, m in rep.errors],
            "warnings": [{"preset": p, "message": m} for p, m in rep.warnings],
            "ok": rep.ok,
        }, ensure_ascii=False, indent=2))
    else:
        for p, m in rep.errors:
            print(f"ERROR  {p}: {m}")
        for p, m in rep.warnings:
            print(f"WARN   {p}: {m}")
        print(f"\n{len(loaded)} presetów, {len(rep.errors)} błędów, {len(rep.warnings)} ostrzeżeń")
        print("OK" if rep.ok else "FAILED")

    return 0 if rep.ok else 1


def main(argv: list[str]) -> int:
    # Ścieżki rozpoznajemy po istnieniu (istniejący katalog), a nie po treści — inaczej preset
    # o nazwie argumentu zostałby pomylony z flagą.
    args: list[str] = []
    for a in argv[1:]:
        if a.startswith("--"):
            continue
        if Path(a).exists():
            args.append(a)
        else:
            print(f"Uwaga: nieznany argument / nieistniejąca ścieżka: {a}", file=sys.stderr)
    as_json = "--json" in argv
    if args:
        # jeżeli podano katalog nadrzędny, waliduj wszystkie jego podkatalogi z preset.yaml
        targets = []
        for a in args:
            p = Path(a).resolve()
            if (p / "preset.yaml").exists():
                targets.append(p)
            else:
                targets.extend(sorted(x for x in p.iterdir() if x.is_dir() and (x / "preset.yaml").exists()))
    else:
        targets = sorted(p for p in ROOT.iterdir() if p.is_dir() and not p.name.startswith("."))
    return run(targets, as_json=as_json)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
