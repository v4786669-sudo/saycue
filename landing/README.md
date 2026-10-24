Strona walidacyjna SayCue. Cel: w 10 sekund przekonać do pobrania, w 60 sekund zebrać sygnał płatnościowy — nie sprzedawać.

## Co jest w środku

```
saycue/
├── server.js                      # lokalny serwer statyczny + collector (Node 18+, bez zależności)
└── landing/
    ├── index.html                 # strona główna (7 sekcji)
    ├── assets/
    │   ├── style.css              # styl, bez zewnętrznych fontów
    │   ├── collector.js           # licznik zdarzeń (4 pola, bez cookies)
    │   └── demo.gif               # ← DO DODANIA (placeholder w HTML do tego czasu)
    └── collector/
        ├── worker.js              # collector (Cloudflare Worker / import w Node)
        ├── test.js               # testy kontraktu prywatności — `node test.js`
        └── README.md              # krótka instrukcja deploy
```

## Uruchomienie lokalne

```bash
cd saycue
node scripts/build-site.mjs       # landing/ → public/
node scripts/dev-server.mjs       # → http://127.0.0.1:8787/ (statyki + /api/events + /api/subscribe)
node landing/collector/test.js    # → OK — 10/10 sprawdzeń przeszło.
node scripts/test-functions.mjs   # → 12/12 (forms: mock D1)
```

W konsoli przeglądarki: `SayCue.preview()` pokazuje ostatnie zdarzenia; `SayCue.track("demo", {surface:"test"})` wysyła ręczne zdarzenie testowe.

## Wdrożenie — Cloudflare Pages (rekomendowane; jeden deployment = statyki + API)

1. `node scripts/build-site.mjs` → katalog `public/`.
2. `npx wrangler pages deploy public --project-name saycue` — Pages wykrywa `functions/` obok `public/`.
3. Binding D1 (`DB`), schemat i sekrety: **`public/README.md`** (krok po kroku: create → migration → secret → deploy).
4. Po wdrożeniu: `BASE=https://<projekt>.pages.dev node scripts/test-functions.mjs` (testy E2E).

**GitHub Pages nie wystarczy** — statyki tak, ale `/api/events` i `/api/subscribe` wymagają Functions (Cloudflare) albo proxy do `node server.js`. Bez backendu strona nadal działa: collector ignoruje 404, formularz pokaże „zapis chwilowo niedostępny".

## Co mierzymy (mapowanie na bramkę G4c/G4d)

| Zdarzenie | Kiedy | Cel |
|---|---|---|
| `page_view` | wejście | baza wizyt |
| `download_click` (surface: hero/footer) | klik przycisku pobierania | **≥20% wizyt → klik** |
| `pricing_section_view` | 35% sekcji cen widoczne | **≥8% widzów → zapis** |
| `waitlist_form_start` / `waitlist_submit` (wants_paid) | formularz | **≥25% pobrań → formularz** |
| `github_click`, `discord_click` | linki zewnętrzne | kanały |

## Zasady prywatności (nienaruszalne)

- Wysyłane są **wyłącznie** pola: `ts`, `event`, `utm_source`, `referrer_domain` (+ identyfikatory `surface`, `wants_paid`).
- **Zero cookies**, zero localStorage do identyfikacji, zero pikseli i zewnętrznych skryptów.
- Collector **odbija** rekordy z e-mailem/telefonem/nazwą i z nieznanymi polami (`400`) — patrz `collector/test.js`.
- **Do Not Track / Global Privacy Control** = całkowita cisza (żadnego zdarzenia).
- E-mail z formularza idzie **wyłącznie** do `/api/subscribe` → tabela D1 `subscribers`; nie jest nigdy wysyłany do `/api/events`. Pilnuje tego test `subscribe: poprawny e-mail → … BEZ wpisu w events`.
- Adres e-mail z formularza **nie idzie do collectora** — trafia do dedykowanego endpointu zapisu (Formspree/Brevo/backend), który wybieramy w W0/W1; do tego czasu formularz potwierdza lokalnie.

## Brakujące elementy do publikacji (checklist)

- [ ] `assets/demo.gif` — 8 s, 960×540, ≤2 MB, 10 fps, bez audio; scenariusz w komentarzach `index.html`
- [ ] Prawdziwe linki GitHub/Discord/privacy@ (obecnie `#` / `example`)
- [x] Endpoint zapisu formularza — **Cloudflare Pages Function `/api/subscribe` + D1**
- [ ] Domena .pl/.com i potwierdzenie nazwy marki
- [ ] Podpięcie collectora na produkcji i test end-to-end w realnej sieci
- [ ] Weryfikacja Lighthouse (cel: ≥95 Performance/Accessibility) i brak żądań do obcych domen (DevTools → Network)
