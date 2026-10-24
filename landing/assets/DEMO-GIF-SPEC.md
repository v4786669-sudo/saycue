# demo.gif — scenariusz i specyfikacja

> Specyfikacja nagrania, które trafia na stronę główną. Scenariusz jest zgodny z komentarzem w `landing/index.html`.
> Plik docelowy: **`saycue/landing/assets/demo.gif`** (kopiowany do `public/assets/` przez `node scripts/build-site.mjs`).

## 1. Parametry techniczne (twarde)

| Parametr | Wartość | Dlaczego |
|---|---|---|
| Czas | **8,0 s ± 0,3 s** | tyle zakłada HTML i PLAN §4 |
| Rozdzielczość | **960 × 540** (16:9) | dopasowane do `aspect-ratio: 16/9` w `.gif-slot` |
| FPS | **10** (80 klatek) | czytelne, mały plik |
| Rozmiar | **≤ 2 MB** | landing ładuje się na telefonie z komórki |
| Dźwięk | **brak** | GIF nie ma audio; nie trzeba licencji muzyki |
| Format | GIF (bez przezroczystości, paleta ≤ 128 kolorów) | zgodność i rozmiar |
| Napisy | **wbudowane w obraz** (PL) | TikTok/YouTube i Reddit grają bez dźwięku |

## 2. Scenariusz (potwierdzam z komentarza HTML)

| Czas | Obraz | Napis na klatce (PL) | Wymaga od nagrywającego |
|---|---|---|---|
| 0,0–1,2 s | OBS na scenie „Starting Soon", kursor poza oknem OBS | *(brak — tylko kontekst)* | widoczny pasek scen OBS |
| 1,2–3,2 s | dymek mówiącego „**scena pvp**", tray: `LISTENING` | `„scena pvp"` | mikrofon w tle |
| 3,2–4,8 s | scena zmienia się na „PVP", tray: `ACTING` → `OK` | `scena zmieniona` | płynne przejście, bez czarnego ekranu |
| 4,8–6,4 s | dymek „**wycisz mikrofon**", ikona mikrofonu w OBS się zmienia | `„wycisz mikrofon"` | operator OBS pokazuje mute na źródle `Mic/Aux` |
| 6,4–8,0 s | dymek „**zapisz replay**", toast tray: `Replay saved` | `replay zapisany` · stopka: **„100% offline · MIT"** | replay buffer musi być włączony |

> **Ważne (spójność z presetem):** mów **„wycisz mikrofon"**, nie samo „wycisz" — gołe „wycisz" celowo nie istnieje w presecie OBS (kolizja z głośnością systemu). Wideo ma uczyć poprawnego słowa.

## 3. Czystość obrazu (żeby nikt nie zgłosił nam „fake demo")

- Tylko **jedna gra/aplikacja** w tle — żadnych prywatnych okien, czatów, nicków, e-maili, tokenów.
- **Bez sklejonych przejść:** dymek jest dodawany w edycji, ale **reakcja OBS musi być na żywo** (inaczej test G4a nas skłamie).
- Kursor nie lata chaotycznie; brak powiadomień Windows/Discord.
- Tray pokazuje ikonę SayCue — jeśli jeszcze nie ma ikony, użyj tymczasowej **nie** logo cudzej aplikacji.
- Było: klatka 8,0 s nie może być czarna (Reddit generuje z niej miniaturę).

## 4. Dostarczenie i podmiana placeholdera

```bash
# 1) umieść nagranie w repo
cp <nagranie> saycue/landing/assets/demo.gif

# 2) podmień placeholder w HTML (jedna zmiana):
#    w landing/index.html znajdź <img src="assets/demo.gif" ... hidden data-demo-img>
#    usuń atrybut `hidden`; (opcjonalnie) usuń blok .gif-placeholder
python3 - <<'PY'
from pathlib import Path
p = Path("saycue/landing/index.html"); s = p.read_text(encoding="utf-8")
s = s.replace('<img src="assets/demo.gif" alt="Krótkie nagranie: komenda głosowa zmienia scenę w OBS i wycisza mikrofon." hidden data-demo-img>',
              '<img src="assets/demo.gif" alt="Krótkie nagranie: komenda głosowa zmienia scenę w OBS i wycisza mikrofon." data-demo-img>')
p.write_text(s, encoding="utf-8")
PY

# 3) przebuduj publikację
node scripts/build-site.mjs
```

**Kontrola po podmianie:** `ls -la public/assets/demo.gif` ≤ 2 MB; w DevTools → Network plik wczytuje się bez błędu; w mobilnym widoku (DevTools 375 px) GIF nie rozjeżdża layoutu.

## 5. Zapasowo (gdy demo nie zdąży na W4)

Placeholder **jest dopuszczalny** — mówi „miejsce na demo" i nie kłamie. Lepiej mieć uczciwy placeholder niż GIF z innego narzędzia. Bramka G4a mierzy **instalacje**, nie wideo; brak GIF-a obniża konwersję, ale nie unieważnia testu.
