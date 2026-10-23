/**
 * SayCue — walidacja zapisu e-maili (waitlist). Współdzielone przez:
 *   - functions/api/subscribe.js   (Cloudflare Pages Functions — PRODUKCJA)
 *   - scripts/dev-server.mjs        (lokalny serwer: Pages Functions + statyki)
 *
 * Zasada z t7: e-mail NIE trafia do collectora zdarzeń. Ten moduł jest jedynym miejscem,
 * które w ogóle widzi adres e-mail.
 *
 * Rejestr zgodności/Ochrony Danych (RODO):
 *   - minimalizacja: zbieramy wyłącznie e-mail + dwa znaki kontekstu wiedzy o paczkach,
 *   - cel: JEDNORAZOWE powiadomienie o publikacji paczek presetów/pałatek + betach,
 *   - przechowywanie: 12 miesięcy albo do usunięcia na prośbę (usuwanie: see cloudflare README),
 *   - bez marketingu osób trzecich, bez profilowania, bez przekazywania innym podmiotom,
 *   - dozwolona rezygnacja: odpowiedź słowem „USUŃ" na kontakt@saycue.
 */

export const MAX_EMAIL_LEN = 254;
export const MAX_BODY = 1024;
export const WAITLIST_RETENTION_MONTHS = 12;

// Heurystyka: celowo restrykcyjna, bo ma tylko odsiać oczywiste śmieci.
const EMAIL_RE = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$/;
const CONTROL_CHARS = /[\u0000-\u001f\u007f]/;

export function normalizeEmail(value) {
  if (typeof value !== "string") return null;
  const email = value.trim().toLowerCase();
  if (!email || email.length > MAX_EMAIL_LEN) return null;
  if (CONTROL_CHARS.test(email)) return null;
  if (!EMAIL_RE.test(email)) return null;
  return email;
}

/** `wants_paid` to celowo tylko flaga — bez profilowania. */
export function normalizeWantsPaid(value) {
  return value === true || value === "1" || value === "true" || value === "yes";
}

export function hashIp(ip, salt) {
  // Do deduplikacji zgłoszeń (jeden e-mail nie wpada 20 razy) bez trzymania IP w plaintext.
  // Tylko hex 64 znaków; nie da się z tego odczytać IP bez soli i całej przestrzeni adresów.
  if (!ip || !salt) return null;
  return { ip, salt };
}

export function jsonResponse(status, body, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
      "x-privacy": "email-stored-for-notifications-only,no-ip-logging,retention-12-months",
      ...extra,
    },
  });
}
