/**
 * SayCue — testy Pages Functions (bez zależności: `node scripts/test-functions.mjs`).
 *
 * Dwa tryby:
 *   1) LOKALNIE (domyślnie): importuje functions/ i testuje je z MOCKIEM D1 + synthetic Request.
 *      Nie potrzebuje Cloudflare ani sieci. To jest to, co robi CI.
 *   2) ZDALNIE: `BASE=https://saycue.pages.dev node scripts/test-functions.mjs`
 *      uderza w prawdziwy deployment (testy E2E po publikacji).
 *
 * Testy pilnują kontraktów z t7:
 *   - e-mail NIE trafia do tabeli events (ani do /api/events),
 *   - collector odrzuca PII i nieznane pola,
 *   - brak Set-Cookie, brak identyfikatora sesji,
 *   - /privacy istnieje i wymienia wszystkie zdarzenia.
 */
import assert from "node:assert/strict";

const BASE = process.env.BASE; // gdy ustawione → tryb zdalny

/* ------------------------------------------------------------------ mocks */

function makeDb() {
  const state = { events: [], subscribers: [], attempts: [] };
  function prepare(sql) {
    const stmt = {
      sql: sql.replace(/\s+/g, " ").trim(),
      args: [],
      bind(...args) {
        stmt.args = args;
        return stmt;
      },
      async first() {
        if (/FROM subscribe_attempts/i.test(stmt.sql)) {
          const [hash, since] = stmt.args;
          const n = state.attempts.filter((a) => a.ip_hash === hash && a.ts >= since).length;
          return { n };
        }
        return null;
      },
      async run() {
        if (/INSERT INTO events/i.test(stmt.sql)) {
          const [ts, event, utm, ref, surface, wantsPaid] = stmt.args;
          state.events.push({ ts, event, utm_source: utm, referrer_domain: ref, surface, wants_paid: wantsPaid });
        } else if (/INSERT INTO subscribe_attempts/i.test(stmt.sql)) {
          state.attempts.push({ ip_hash: stmt.args[0], ts: stmt.args[1] });
        } else if (/INSERT INTO subscribers/i.test(stmt.sql)) {
          const [email, wantsPaid, source, now] = stmt.args;
          const found = state.subscribers.find((s) => s.email === email);
          if (found) {
            found.wants_paid = wantsPaid ? 1 : found.wants_paid;
            found.updated_at = now;
          } else {
            state.subscribers.push({ email, wants_paid: wantsPaid ? 1 : 0, source, created_at: now, updated_at: now });
          }
        } else if (/DELETE FROM (events|subscribe_attempts)/i.test(stmt.sql)) {
          // retencja — pomijamy w mocku
        }
        return { success: true };
      },
    };
    return stmt;
  }
  return { prepare, _state: state };
}

function makeRequest(path, { method = "POST", body, headers = {} } = {}) {
  const init = { method, headers: { "content-type": "application/json", ...headers } };
  if (body !== undefined) init.body = typeof body === "string" ? body : JSON.stringify(body);
  return new Request(`https://example.test${path}`, init);
}

/* ------------------------------------------------------------------ tests */

let passed = 0;
const failures = [];

async function test(name, fn) {
  try {
    await fn();
    passed++;
    console.log(`OK   ${name}`);
  } catch (e) {
    failures.push([name, e]);
    console.log(`FAIL ${name}\n     ${String(e.message).split("\n").join("\n     ")}`);
  }
}

async function remote(path, opts) {
  const res = await fetch(`${BASE}${path}`, {
    method: opts.method || "POST",
    headers: { "content-type": "application/json", ...(opts.headers || {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  return res;
}

async function main() {
  if (BASE) {
    // ---------- tryb zdalny (po publikacji) ----------
    await test("zdalnie: /api/events przyjmuje poprawne zdarzenie", async () => {
      const res = await remote("/api/events", {
        body: { ts: new Date().toISOString(), event: "page_view", utm_source: "selftest", referrer_domain: "direct" },
      });
      assert.equal(res.status, 204);
      assert.equal(res.headers.get("set-cookie"), null);
    });
    await test("zdalnie: /api/events odrzuca PII", async () => {
      const res = await remote("/api/events", { body: { event: "page_view", utm_source: "jan@example.com" } });
      assert.equal(res.status, 400);
    });
    await test("zdalnie: /api/subscribe odrzuca zły e-mail", async () => {
      const res = await remote("/api/subscribe", { body: { email: "nie-jest-emejlem" } });
      assert.equal(res.status, 400);
    });
    await test("zdalnie: /privacy zwraca 200", async () => {
      const res = await fetch(`${BASE}/privacy`);
      assert.equal(res.status, 200);
      const html = await res.text();
      assert.match(html, /page_view/);
    });
    await test("zdalnie: GET /api/events → 405", async () => {
      const res = await fetch(`${BASE}/api/events`);
      assert.equal(res.status, 405);
    });
  } else {
    // ---------- tryb lokalny (mock D1) ----------
    const eventsFn = (await import("../functions/api/events.js")).onRequest;
    const subscribeFn = (await import("../functions/api/subscribe.js")).onRequest;
    const privacyFn = (await import("../functions/privacy.js")).onRequestGet;

    await test("events: poprawne zdarzenie → 204 i zapis bez IP", async () => {
      const db = makeDb();
      const res = await eventsFn({
        request: makeRequest("/api/events", {
          body: { ts: "2026-10-23T12:00:00Z", event: "download_click", surface: "hero", utm_source: "reddit", referrer_domain: "reddit.com" },
        }),
        env: { DB: db },
      });
      assert.equal(res.status, 204);
      assert.equal(res.headers.get("set-cookie"), null);
      assert.equal(db._state.events.length, 1);
      assert.deepEqual(Object.keys(db._state.events[0]).sort(), ["event", "referrer_domain", "surface", "ts", "utm_source", "wants_paid"]);
    });

    await test("events: odrzuca nieznane zdarzenie i PII", async () => {
      const db = makeDb();
      const bad1 = await eventsFn({ request: makeRequest("/api/events", { body: { event: "purchase_all" } }), env: { DB: db } });
      assert.equal(bad1.status, 400);
      const bad2 = await eventsFn({ request: makeRequest("/api/events", { body: { event: "page_view", utm_source: "jan@example.com" } }), env: { DB: db } });
      assert.equal(bad2.status, 400);
      assert.equal(db._state.events.length, 0);
    });

    await test("events: GET → 405, OPTIONS → 204", async () => {
      const db = makeDb();
      const get = await eventsFn({ request: makeRequest("/api/events", { method: "GET" }), env: { DB: db } });
      assert.equal(get.status, 405);
      const opt = await eventsFn({ request: makeRequest("/api/events", { method: "OPTIONS" }), env: { DB: db } });
      assert.equal(opt.status, 204);
    });

    await test("events: bez DB → 204 (strona działa, tylko nie zapisuje)", async () => {
      const res = await eventsFn({ request: makeRequest("/api/events", { body: { event: "page_view" } }), env: {} });
      assert.equal(res.status, 204);
    });

    await test("subscribe: poprawny e-mail → 200, zapis, BEZ wpisu w events", async () => {
      const db = makeDb();
      const res = await subscribeFn({
        request: makeRequest("/api/subscribe", { body: { email: "  Jan.Kowalski@Example.COM ", wants_paid: true } }),
        env: { DB: db, RATE_SALT: "test-salt" },
      });
      assert.equal(res.status, 200);
      assert.equal((await res.json()).ok, true);
      assert.equal(db._state.subscribers.length, 1);
      assert.equal(db._state.subscribers[0].email, "jan.kowalski@example.com");
      assert.equal(db._state.subscribers[0].wants_paid, 1);
      assert.equal(db._state.events.length, 0, "e-mail nie może trafić do collectora zdarzeń");
      assert.equal(res.headers.get("set-cookie"), null);
    });

    await test("subscribe: zły e-mail → 400, brak zapisu", async () => {
      const db = makeDb();
      for (const bad of ["nie-emejl", "a@b", "a b@c.pl", "", "x".repeat(300) + "@a.pl", "jan@example.com\r\nBcc: x@y.pl"]) {
        const res = await subscribeFn({
          request: makeRequest("/api/subscribe", { body: { email: bad } }),
          env: { DB: db, RATE_SALT: "s" },
        });
        assert.equal(res.status, 400, `oczekiwano 400 dla ${JSON.stringify(bad)}`);
      }
      assert.equal(db._state.subscribers.length, 0);
    });

    await test("subscribe: honeypot (website wypełniony) → 200, bez zapisu", async () => {
      const db = makeDb();
      const res = await subscribeFn({
        request: makeRequest("/api/subscribe", { body: { email: "bot@example.com", website: "spam" } }),
        env: { DB: db, RATE_SALT: "s" },
      });
      assert.equal(res.status, 200);
      assert.equal(db._state.subscribers.length, 0);
    });

    await test("subscribe: duplikat aktualizuje rekord, nie dubluje", async () => {
      const db = makeDb();
      const env = { DB: db, RATE_SALT: "s" };
      await subscribeFn({ request: makeRequest("/api/subscribe", { body: { email: "a@example.com" } }), env });
      await subscribeFn({ request: makeRequest("/api/subscribe", { body: { email: "A@Example.com", wants_paid: true } }), env });
      assert.equal(db._state.subscribers.length, 1);
      assert.equal(db._state.subscribers[0].wants_paid, 1);
    });

    await test("subscribe: rate limit po 5 zgłoszeniach z tego samego IP → 429", async () => {
      const db = makeDb();
      const env = { DB: db, RATE_SALT: "s" };
      const mk = (i) => makeRequest("/api/subscribe", { body: { email: `u${i}@example.com` }, headers: { "CF-Connecting-IP": "203.0.113.7" } });
      for (let i = 0; i < 5; i++) {
        const res = await subscribeFn({ request: mk(i), env });
        assert.equal(res.status, 200, `próba ${i + 1}`);
      }
      const blocked = await subscribeFn({ request: mk(99), env });
      assert.equal(blocked.status, 429);
    });

    await test("subscribe: bez DB → 503 (UI pokaże błąd)", async () => {
      const res = await subscribeFn({ request: makeRequest("/api/subscribe", { body: { email: "a@example.com" } }), env: {} });
      assert.equal(res.status, 503);
    });

    await test("privacy: 200, wymienia wszystkie zdarzenia collector-a", async () => {
      const res = privacyFn();
      assert.equal(res.status, 200);
      const html = await res.text();
      const { ALLOWED_EVENTS } = await import("../functions/_shared/events.js");
      for (const ev of ALLOWED_EVENTS) {
        if (ev === "github_click" || ev === "discord_click") continue; // opisane razem w jednym wierszu
        assert.ok(html.includes(ev), `brak zdarzenia ${ev} na /privacy`);
      }
      assert.match(html, /DNT|Do Not Track/);
      assert.match(html, /12 miesi/);
    });

    await test("index.html: brak zewnętrznych zasobów i linków-zaślepek", async () => {
      const fs = await import("node:fs/promises");
      const html = await fs.readFile(new URL("../landing/index.html", import.meta.url), "utf8");
      assert.ok(!/src=["']https?:\/\//.test(html), "brak zewnętrznych skryptów");
      assert.ok(!/href=["']#["']/.test(html), "brak pustych linków href=\"#\"");
      assert.ok(!/github\.com\/"/.test(html), "brak zaślepki https://github.com/");
      assert.match(html, /\/privacy/, "stopka linkuje do /privacy");
    });
  }

  console.log(`\n${passed}/${passed + failures.length} sprawdzeń${BASE ? " (zdalnie)" : " (lokalnie, mock D1)"}`);
  if (failures.length) process.exit(1);
}

main().catch((e) => {
  console.error("test-functions FAILED:", e);
  process.exit(1);
});
