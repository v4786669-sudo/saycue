/**
 * Testy collectors (bez zależności; `node --test` albo `node test.js`).
 * Sprawdzają kontrakt prywatności: cztery pola, brak PII, brak ciasteczek, whitelist zdarzeń.
 */
import assert from "node:assert/strict";
import { handle, validate, ALLOWED } from "./worker.js";

const enc = (obj) => new TextEncoder().encode(JSON.stringify(obj));
const req = (body, method = "POST") =>
  new Request("https://example.test/api/events", {
    method,
    body: method === "GET" ? undefined : enc(body),
    headers: { "content-type": "application/json" },
  });

let passed = 0;
const tests = [];
const test = (name, fn) => tests.push({ name, fn });

test("akceptuje poprawny rekord (4 pola)", async () => {
  const r = await handle(req({ ts: "2026-10-23T12:00:00Z", event: "page_view", utm_source: "reddit", referrer_domain: "reddit.com" }), {});
  assert.equal(r.status, 204);
  assert.equal(r.headers.get("set-cookie"), null, "collector nie może ustawiać cookies");
  passed++;
});

test("odrzuca nieznane zdarzenie", async () => {
  const r = await handle(req({ event: "purchase_everything" }), {});
  assert.equal(r.status, 400);
  assert.match((await r.json()).error, /event_not_allowed/);
  passed++;
});

test("odrzuca e-mail w polu", async () => {
  const r = await handle(req({ event: "page_view", utm_source: "jan.kowalski@example.com" }), {});
  assert.equal(r.status, 400);
  assert.match((await r.json()).error, /possible_pii|unsafe_chars/);
  passed++;
});

test("odrzuca numer telefonu", async () => {
  const r = await handle(req({ event: "page_view", referrer_domain: "+48 600 123 456" }), {});
  assert.equal(r.status, 400);
  passed++;
});

test("odrzuca dodatkowe pole (np. ip, email, session_id)", async () => {
  for (const extra of [{ ip: "1.2.3.4" }, { email: "a@b.pl" }, { session_id: "abc" }]) {
    const r = await handle(req({ event: "page_view", ...extra }), {});
    assert.equal(r.status, 400);
  }
  passed++;
});

test("odrzuca GET/OPTIONS zgodnie z kontraktem", async () => {
  assert.equal((await handle(req(null, "GET"), {})).status, 405);
  assert.equal((await handle(req(null, "OPTIONS"), {})).status, 204);
  passed++;
});

test("odrzuca ciało > 512 B", async () => {
  const r = await handle(req({ event: "page_view", utm_source: "x".repeat(600) }), {});
  assert.equal(r.status, 413);
  passed++;
});

test("validate() zwraca null dla pełnego dozwolonego zestawu", () => {
  const e = { ts: "2026-10-23T12:00:00.000Z", event: "waitlist_submit", utm_source: "reddit", referrer_domain: "reddit.com", wants_paid: "yes" };
  assert.equal(validate(e), null);
  assert.ok(ALLOWED.has("waitlist_submit"));
  passed++;
});

test("odpowiedź nie zawiera nagłówka z IP ani cookies", async () => {
  const r = await handle(req({ event: "pricing_section_view" }), {});
  assert.equal(r.headers.get("set-cookie"), null);
  assert.equal(r.headers.get("x-privacy"), "no-cookies,no-ip-logging,pseudonymous");
  passed++;
});

test("sink: rekord przekazany do SINK_URL ma dokładnie 4–6 dozwolonych pól", async () => {
  let captured = null;
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (_url, init) => {
    captured = JSON.parse(init.body);
    return new Response("", { status: 204 });
  };
  try {
    await handle(req({ ts: "2026-10-23T12:00:00Z", event: "download_click", surface: "hero", utm_source: "github", referrer_domain: "github.com" }),
      { SINK_URL: "https://sink.test/collect" });
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert.deepEqual(Object.keys(captured).sort(), ["event", "referrer_domain", "surface", "ts", "utm_source"]);
  assert.equal(captured.surface, "hero");
  passed++;
});

// ---- runner ----
for (const t of tests) await t.fn();
console.log(`OK — ${passed}/${tests.length} sprawdzeń przeszło.`);
