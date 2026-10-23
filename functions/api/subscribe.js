/**
 * SayCue — zapis zgłoszeń z formularza (Cloudflare Pages Function).
 * Endpoint: POST /api/subscribe
 *
 * Odpowiedzi:
 *   200 { ok: true }        — zapisane (albo zaktualizowane)
 *   400 { ok: false, error } — zły e-mail
 *   405                      — inna metoda
 *   413                      — ciało > 1024 B
 *   429                      — rate limit na hashu IP (5 zgłoszeń / 10 min)
 *   503                      — brak bazy (env.DB) — formularz poinformuje o błędzie
 *
 * Prywatność: adres trafia WYŁĄCZNIE do D1 (tabela `subscribers`) — nigdy do collector-a
 * zdarzeń (/api/events). Nie logujemy IP; zamiast tego zapisujemy skrócony hash do dedup.
 */
import {
  MAX_BODY,
  normalizeEmail,
  normalizeWantsPaid,
  jsonResponse,
} from "../_shared/subscribe.js";

const RATE_WINDOW_SECONDS = 600;
const RATE_MAX = 5;

async function sha256(value) {
  const data = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function clientIp(request) {
  return request.headers.get("CF-Connecting-IP") || "";
}

async function checkRateLimit(db, ipHash, salt) {
  if (!ipHash || !salt) return true; // brak IP → nie blokujemy (Cloudflare zawsze go daje)
  const hash = await sha256(`${salt}:${ipHash}`);
  const since = new Date(Date.now() - RATE_WINDOW_SECONDS * 1000).toISOString();
  const row = await db
    .prepare("SELECT COUNT(*) AS n FROM subscribe_attempts WHERE ip_hash = ?1 AND ts >= ?2")
    .bind(hash, since)
    .first();
  if ((row?.n ?? 0) >= RATE_MAX) return false;
  await db
    .prepare("INSERT INTO subscribe_attempts (ip_hash, ts) VALUES (?1, ?2)")
    .bind(hash, new Date().toISOString())
    .run();
  await db.prepare("DELETE FROM subscribe_attempts WHERE ts < ?1").bind(since).run();
  return true;
}

export async function onRequest({ request, env }) {
  if (request.method === "OPTIONS") return new Response(null, { status: 204 });
  if (request.method !== "POST") return jsonResponse(405, { ok: false, error: "method_not_allowed" });

  const raw = await request.text();
  if (!raw || raw.length > MAX_BODY) return jsonResponse(413, { ok: false, error: "body_too_large" });

  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    return jsonResponse(400, { ok: false, error: "bad_json" });
  }

  // honeypot: boty wypełniają ukryte pole `website`; ludzie go nie widzą
  if (payload.website) return jsonResponse(200, { ok: true });

  const email = normalizeEmail(payload.email);
  if (!email) return jsonResponse(400, { ok: false, error: "invalid_email" });

  const wantsPaid = normalizeWantsPaid(payload.wants_paid);
  const db = env?.DB;

  if (!db) {
    // brak bazy = brak możliwości zapisu; UI pokaże "spróbuj ponownie"
    return jsonResponse(503, { ok: false, error: "storage_unavailable" });
  }

  const allowed = await checkRateLimit(db, clientIp(request), env.RATE_SALT);
  if (!allowed) return jsonResponse(429, { ok: false, error: "rate_limited" });

  const now = new Date().toISOString();
  await db
    .prepare(
      `INSERT INTO subscribers (email, wants_paid, source, created_at, updated_at)
       VALUES (?1, ?2, ?3, ?4, ?4)
       ON CONFLICT(email) DO UPDATE SET
         wants_paid = CASE WHEN excluded.wants_paid = 1 THEN 1 ELSE subscribers.wants_paid END,
         updated_at = excluded.updated_at`
    )
    .bind(email, wantsPaid ? 1 : 0, String(payload.source || "landing").slice(0, 32), now)
    .run();

  return jsonResponse(200, { ok: true });
}
