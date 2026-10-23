/**
 * SayCue — collector zdarzeń (Cloudflare Pages Function).
 * Endpoint: POST /api/events   → zapis do D1 (tabela `events`), odpowiedź 204.
 *
 * Zasada: wyłącznie {ts, event, utm_source, referrer_domain} (+ surface, wants_paid).
 * Nie zapisujemy IP, nie ustawiamy cookies. Bez D1 (env.DB) → 204 i nic nie zapisujemy
 * (bezpieczny default, strona dalej działa).
 */
import { handleEventRequest } from "../_shared/events.js";

export async function onRequest({ request, env }) {
  const db = env?.DB;
  const sink = db
    ? async (record) => {
        await db
          .prepare(
            `INSERT INTO events (ts, event, utm_source, referrer_domain, surface, wants_paid)
             VALUES (?1, ?2, ?3, ?4, ?5, ?6)`
          )
          .bind(
            record.ts,
            record.event,
            record.utm_source,
            record.referrer_domain,
            record.surface ?? null,
            record.wants_paid ?? null
          )
          .run();
        // retencja: 180 dni (RODO — minimalizacja; SQL z README collectora)
        await db
          .prepare("DELETE FROM events WHERE ts < ?1")
          .bind(new Date(Date.now() - 180 * 86400_000).toISOString())
          .run();
      }
    : null;

  return handleEventRequest(request, sink, { allowOrigin: env?.ALLOW_ORIGIN || "*" });
}
