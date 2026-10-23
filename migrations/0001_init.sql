-- SayCue — schemat D1 dla strony walidacyjnej (Cloudflare Pages Functions).
-- Uruchomienie: npx wrangler d1 execute saycue-events --remote --file=migrations/0001_init.sql
--
-- Zasady prywatności (patrz /privacy i functions/_shared/*.js):
--   - events:      cztery pola + identyfikatory; BEZ IP, BEZ cookies, retencja 180 dni
--   - subscribers: e-mail WYŁĄCZNIE do powiadomień; retencja 12 miesięcy; dostęp do usunięcia
--   - subscribe_attempts: hash IP z solą, wyłącznie do rate limitu; wpisy wygasają po 10 min

CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  event TEXT NOT NULL,
  utm_source TEXT NOT NULL DEFAULT 'direct',
  referrer_domain TEXT NOT NULL DEFAULT 'unknown',
  surface TEXT,
  wants_paid TEXT
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events (ts);
CREATE INDEX IF NOT EXISTS idx_events_name_ts ON events (event, ts);

CREATE TABLE IF NOT EXISTS subscribers (
  email TEXT PRIMARY KEY COLLATE NOCASE,
  wants_paid INTEGER NOT NULL DEFAULT 0,
  source TEXT NOT NULL DEFAULT 'landing',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  unsubscribed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_subscribers_created ON subscribers (created_at);

CREATE TABLE IF NOT EXISTS subscribe_attempts (
  ip_hash TEXT NOT NULL,
  ts TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_attempts_hash_ts ON subscribe_attempts (ip_hash, ts);

-- Zgodność: tabela musi być MAŁA (rate limit) — czyszczenie przy każdym zapisie w subscribe.js.
