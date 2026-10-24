# Collector zdarzeń — instrukcja wdrożenia

Collector przyjmuje **wyłącznie**: `{ts, event, utm_source, referrer_domain}` (+ `surface`, `wants_paid` jako identyfikatory). Nie zapisuje IP, nie ustawia cookies, odrzuca rekordy z PII i nieznanymi polami.

## Testy

```bash
node landing/collector/test.js
# OK — 10/10 sprawdzeń przeszło.
```

## Opcja A — Cloudflare Workers

```bash
cd saycue/landing/collector
npx wrangler deploy worker.js --name saycue-events
```

Konfiguracja (opcjonalna) w `wrangler.toml`:

```toml
name = "saycue-events"
main = "worker.js"
compatibility_date = "2026-10-01"

[vars]
ALLOW_ORIGIN = "https://saycue.example"   # ogranicz CORS do własnej domeny
# SINK_URL = "https://twoj-endpoint.zapisu/events"   # opcjonalnie: przekierowanie do D1/webhook
```

Sekrety: `wrangler secret put SINK_TOKEN` (jeśli sink wymaga autoryzacji).

## Opcja B — Node na VPS

```bash
cd saycue
node server.js 8787     # statyki + /api/events
```

Za reverse-proxy (Caddy):

```
saycue.example {
    root * /var/www/saycue/landing
    handle /api/events {
        reverse_proxy 127.0.0.1:8787
    }
    file_server
}
```

## Gdzie trafiają dane

Brak `SINK_URL` → worker odpowiada 204 i **niczego nie zapisuje** (bezpieczny default; przydaje się do testów UI).
Z `SINK_URL` → rekord JSON trafia do twojego endpointu. Rekomendacja: **D1 / SQLite** ze schematem:

```sql
CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  event TEXT NOT NULL,
  utm_source TEXT,
  referrer_domain TEXT,
  surface TEXT,
  wants_paid TEXT,
  CHECK (event IN ('page_view','download_click','github_click','discord_click',
                   'gif_placeholder_click','pricing_section_view','waitlist_form_start','waitlist_submit'))
);
-- Brak kolumny IP. Retencja: usuwaj rekordy starsze niż 180 dni (cron).
DELETE FROM events WHERE ts < datetime('now', '-180 days');
```

## Podgląd metryk strony

```sql
-- ≥20% wizyt → klik pobierania
SELECT
  (SELECT COUNT(*) FROM events WHERE event='download_click') * 1.0 /
  NULLIF((SELECT COUNT(DISTINCT id) FROM events WHERE event='page_view'), 0) AS download_rate;

-- ≥8% widzów sekcji cen → zapis
SELECT COUNT(*) FROM events WHERE event='waitlist_submit';   -- zestaw z pricing_section_view

-- ≥25% pobrań → formularz
SELECT
  (SELECT COUNT(*) FROM events WHERE event='waitlist_submit') * 1.0 /
  NULLIF((SELECT COUNT(*) FROM events WHERE event='download_click'), 0) AS form_rate;
```

> Uwaga: `page_view` nie ma identyfikatora wizyty z założenia (brak cookies) — wskaźnik „% wizyt" liczymy jako **unikalne wejścia per referrer/dzień** lub przez Cloudflare Analytics (agregat, bez cookies). Do pierwszego tygodnia wystarczy porównanie surowych liczników — i tak służy to tylko do progu G4c, nie do raportu inwestorskiego.
