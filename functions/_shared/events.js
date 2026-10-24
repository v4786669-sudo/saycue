/**
 * SayCue — walidacja zdarzeń collector-a. Współdzielona przez:
 *   - functions/api/events.js   (Cloudflare Pages Functions — PRODUKCJA)
 *   - landing/collector/worker.js (standalone Worker / Node — lokalnie i na VPS)
 *
 * Kontrakt: przyjmujemy WYŁĄCZNIE
 *   { ts, event, utm_source, referrer_domain }  (+ identyfikatory: surface, wants_paid)
 * i nic więcej. Odrzucamy: nieznane zdarzenia, nieznane pola, cokolwiek podobnego do PII.
 *
 * Zero zależności: czysty JS/ESM (działa w Workers i w Node 18+).
 */

export const ALLOWED_EVENTS = new Set([
  "page_view",
  "download_click",
  "github_click",
  "discord_click",
  "gif_placeholder_click",
  "pricing_section_view",
  "waitlist_form_start",
  "waitlist_submit",
]);

export const MAX_BODY = 512;
export const ALLOWED_KEYS = new Set(["ts", "event", "utm_source", "referrer_domain", "surface", "wants_paid"]);

const SAFE_STRING = /^[A-Za-z0-9\-_.:\/@ ]{1,80}$/;
// cokolwiek przypominającego dane osobowe → odrzucenie, nie oczyszczanie
const PII_HINT = /(@.+\.(com|pl|net|org|io|eu|de|uk)\b|\+?\d[\d ]{8,}|[A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]+\s+[A-ZŁŚŻŹĆŃÓ][a-ząćęłńóśźż]+)/;

/**
 * @param {unknown} raw
 * @returns {string|null} nazwa problemu albo null, gdy rekord poprawny
 */
export function validateEvent(raw) {
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
  if (!ALLOWED_EVENTS.has(raw.event)) return `event_not_allowed:${raw.event}`;
  if (raw.ts && !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(raw.ts)) return "bad_ts";
  return null;
}

/** Rekord wynikowy — dokładnie te pola, bez IP i bez nagłówków przeglądarki. */
export function normalizeEvent(raw) {
  const record = {
    ts: raw.ts || new Date().toISOString(),
    event: raw.event,
    utm_source: raw.utm_source || "direct",
    referrer_domain: raw.referrer_domain || "unknown",
  };
  if (raw.surface) record.surface = raw.surface;
  if (raw.wants_paid) record.wants_paid = raw.wants_paid;
  return record;
}

export function privacyHeaders(extra = {}) {
  return {
    "content-type": "application/json; charset=utf-8",
    "cache-control": "no-store",
    // jawna deklaracja: zero cookies, zero identyfikatorów
    "x-privacy": "no-cookies,no-ip-logging,pseudonymous",
    ...extra,
  };
}

export function jsonResponse(status, body, extra = {}) {
  return new Response(JSON.stringify(body), { status, headers: privacyHeaders(extra) });
}

/**
 * Wspólna obsługa POST /api/events: waliduje, a zapis deleguje do `sink(record)`.
 * @param {Request} request
 * @param {(record:Record<string,string>) => Promise<void>} [sink]
 * @param {{ allowOrigin?: string }} [opts]
 */
export async function handleEventRequest(request, sink, opts = {}) {
  const cors = {
    "access-control-allow-origin": opts.allowOrigin || "*",
    "access-control-allow-methods": "POST, OPTIONS",
    "access-control-allow-headers": "content-type",
    "access-control-max-age": "86400",
  };

  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });
  if (request.method !== "POST") return jsonResponse(405, { ok: false, error: "method_not_allowed" }, cors);

  let text;
  try {
    text = await request.text();
  } catch {
    return jsonResponse(400, { ok: false, error: "unreadable_body" }, cors);
  }
  if (!text || text.length > MAX_BODY) return jsonResponse(413, { ok: false, error: "body_too_large" }, cors);

  let raw;
  try {
    raw = JSON.parse(text);
  } catch {
    return jsonResponse(400, { ok: false, error: "bad_json" }, cors);
  }

  const problem = validateEvent(raw);
  if (problem) return jsonResponse(400, { ok: false, error: problem }, cors);

  const record = normalizeEvent(raw);
  if (sink) {
    try {
      await sink(record);
    } catch {
      // Nie blokujemy odpowiedzi dla przeglądarki — strata pojedynczego zdarzenia jest OK.
    }
  }

  return new Response(null, { status: 204, headers: { ...privacyHeaders(), ...cors } });
}
