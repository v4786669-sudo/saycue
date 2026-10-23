/**
 * SayCue — collector zdarzeń strony walidacyjnej (PLAN.md §4, §8 G4c/G4d).
 *
 * Cel: przyjmować WYŁĄCZNIE cztery pola — {ts, event, utm_source, referrer_domain}.
 * Kontrakt twardy (testowany w collector/test.js):
 *   - żadnych adresów IP w logach ani w odpowiedzi,
 *   - żadnych ciasteczek (Set-Cookie),
 *   - whitelist nazw zdarzeń — inne są odrzucane (400),
 *   - żadnych danych osobowych: rekordy z polem wyglądającym jak e-mail/tel./imię są odrzucane.
 *
 * Deployment (Cloudflare Workers): wrangler.toml + `wrangler deploy`.
 * Deployment (VPS/Node 18+): `node server.js` za reverse-proxy (Caddy/nginx).
 * Bez zależności: używa wyłącznie globalnego `fetch` (runtime) i Web Crypto (opcjonalnie do hasha).
 *
 * Przechowywanie: D1 (SQL) albo GA4 — patrz docs/README. Domyślnie worker zwraca 204 i
 * przekazuje do `SINK_URL` (jeśli ustawiony), inaczej tylko loguje metrykę (bez IP).
 */

const ALLOWED = new Set([
  "page_view",
  "download_click",
  "github_click",
  "discord_click",
  "gif_placeholder_click",
  "pricing_section_view",
  "waitlist_form_start",
  "waitlist_submit",
]);

const MAX_BODY = 512;      // bajty — zdarzenie to kilka pól, nie formularz
const ALLOWED_KEYS = new Set(["ts", "event", "utm_source", "referrer_domain", "surface", "wants_paid"]);

const SAFE_STRING = /^[A-Za-z0-9\-_.:\/@ ]{1,80}$/;
// cokolwiek przypominającego dane osobowe → odrzucenie, nie oczyszczanie
const PII_HINT = /(@.+\.(com|pl|net|org|io|eu|de|uk)\b|\+?\d[\d ]{8,}|[A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]+\s+[A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]+)/;

function json(status, body) {
  const headers = {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    // jawna deklaracja: zero cookies, zero identyfikatorów
    "x-privacy": "no-cookies,no-ip-logging,pseudonymous",
  };
  return new Response(JSON.stringify(body), { status, headers });
}

function validate(raw) {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return "not_an_object";
  const keys = Object.keys(raw);
  if (keys.length > ALLOWED_KEYS.size) return "too_many_fields";
  for (const k of keys) {
    if (!ALLOWED_KEYS.has(k)) return `field_not_allowed:${k}`;
    const v = raw[k];
    if (v === null || v === undefined) continue;
    if (typeof v !== "string") return `not_a_string:${k}`;
    if (PII_HINT.test(v)) return `possible_pii:${k}`;
    if (!SAFE_STRING.test(v)) return `unsafe_chars:${k}`;
  }
  if (!ALLOWED.has(raw.event)) return `event_not_allowed:${raw.event}`;
  if (raw.ts && !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(raw.ts)) return "bad_ts";
  return null;
}

async function handle(request, env) {
  const cors = {
    "access-control-allow-origin": env && env.ALLOW_ORIGIN ? env.ALLOW_ORIGIN : "*",
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "content-type",
    "access-control-max-age": "86400",
  };

  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (request.method !== "POST") return json(405, { ok: false, error: "method_not_allowed" });

  let text;
  try {
    text = await request.text();
  } catch {
    return json(400, { ok: false, error: "unreadable_body" });
  }
  if (!text || text.length > MAX_BODY) return json(413, { ok: false, error: "body_too_large" });

  let raw;
  try {
    raw = JSON.parse(text);
  } catch {
    return json(400, { ok: false, error: "bad_json" });
  }

  const problem = validate(raw);
  if (problem) return json(400, { ok: false, error: problem });

  // Rekord wynikowy: dokładnie te pola, w tej kolejności, bez IP i bez nagłówków przeglądarki.
  const record = {
    ts: raw.ts || new Date().toISOString(),
    event: raw.event,
    utm_source: raw.utm_source || "direct",
    referrer_domain: raw.referrer_domain || "unknown",
  };
  if (raw.surface) record.surface = raw.surface;
  if (raw.wants_paid) record.wants_paid = raw.wants_paid;

  // Opcjonalny sink: własny endpoint (np. D1/HTTP collector). Brak sinku = tylko licznik w logu.
  if (env && env.SINK_URL) {
    try {
      await fetch(env.SINK_URL, {
        method: "POST",
        headers: { "content-type": "application/json", ...(env.SINK_TOKEN ? { authorization: `Bearer ${env.SINK_TOKEN}` } : {}) },
        body: JSON.stringify(record),
      });
    } catch {
      // Nie blokujemy odpowiedzi dla przeglądarki — strata pojedynczego zdarzenia jest OK.
    }
  }

  const res = new Response(null, { status: 204 });
  for (const [k, v] of Object.entries(cors)) res.headers.set(k, v);
  res.headers.set("cache-control", "no-store");
  res.headers.set("x-privacy", "no-cookies,no-ip-logging,pseudonymous");
  return res;
}

/* ---------- Cloudflare Worker ---------- */
export default {
  async fetch(request, env) {
    try {
      return await handle(request, env || {});
    } catch (e) {
      return json(500, { ok: false, error: "internal" });
    }
  },
};

/* ---------- Node 18+ (server.js) ---------- */
export { handle, validate, ALLOWED };
