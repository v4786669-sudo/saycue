/**
 * SayCue — lokalny serwer deweloperski: statyki z `public/` + te same Functions co produkcja.
 * Uruchomienie: node scripts/dev-server.mjs [port]     (domyślnie 8787)
 *
 * Nie zastępuje `wrangler pages dev` (CI i produkcja używają Cloudflare), ale wystarcza do
 * pracy nad landingiem bez instalowania wranglera. Handler-y importujemy z `functions/`,
 * więc testujesz DOKŁADNIE ten kod, który pojedzie na produkcję.
 */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { onRequest as eventsHandler } from "../functions/api/events.js";
import { onRequest as subscribeHandler } from "../functions/api/subscribe.js";
import { onRequestGet as privacyHandler } from "../functions/privacy.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PUBLIC = path.join(ROOT, "public");
const PORT = Number(process.argv[2] || process.env.PORT || 8787);

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".gif": "image/gif",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".ico": "image/x-icon",
  ".json": "application/json; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
};

function toWebRequest(req, url, body) {
  const headers = {};
  for (const [k, v] of Object.entries(req.headers)) headers[k] = Array.isArray(v) ? v.join(", ") : v;
  return new Request(`http://localhost${url.pathname}`, {
    method: req.method,
    headers,
    body: req.method === "GET" || req.method === "HEAD" ? undefined : body,
  });
}

async function sendWebResponse(res, webRes) {
  const headers = {};
  webRes.headers.forEach((v, k) => { headers[k] = v; });
  res.writeHead(webRes.status, headers);
  const body = await webRes.text();
  res.end(body || undefined);
}

function handleStatic(req, res, url) {
  const rel = url.pathname === "/" ? "index.html" : decodeURIComponent(url.pathname).replace(/^\/+/, "");
  const file = path.resolve(PUBLIC, rel);
  if (!file.startsWith(PUBLIC + path.sep)) {
    res.writeHead(403, { "content-type": "text/plain" });
    return res.end("forbidden");
  }
  fs.readFile(file, (err, data) => {
    if (err) {
      if (rel !== "index.html") {
        res.writeHead(404, { "content-type": "text/html; charset=utf-8" });
        return res.end("<!doctype html><meta charset=utf-8><title>404</title><p>Nie ma tu nic. <a href='/'>Wróć</a></p>");
      }
      res.writeHead(500, { "content-type": "text/plain" });
      return res.end("public/index.html nie istnieje — uruchom: node scripts/build-site.mjs");
    }
    res.writeHead(200, {
      "content-type": MIME[path.extname(file)] || "application/octet-stream",
      "cache-control": "no-store",
    });
    res.end(data);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  const isApi = url.pathname.startsWith("/api/");

  if (url.pathname === "/privacy") {
    return sendWebResponse(res, privacyHandler());
  }

  if (isApi) {
    if (req.method === "OPTIONS") {
      res.writeHead(204, {
        "access-control-allow-origin": "*",
        "access-control-allow-methods": "POST, OPTIONS",
        "access-control-allow-headers": "content-type",
      });
      return res.end();
    }
    const body = await new Promise((resolve) => {
      const chunks = [];
      req.on("data", (c) => chunks.push(c));
      req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    });
    const request = toWebRequest(req, url, body);
    // Lokalnie: brak D1 → events zwraca 204 (bez zapisu), subscribe zwraca 503 (UI pokaże błąd).
    const env = { ALLOW_ORIGIN: "*" };
    try {
      if (url.pathname === "/api/events") return await sendWebResponse(res, await eventsHandler({ request, env }));
      if (url.pathname === "/api/subscribe") return await sendWebResponse(res, await subscribeHandler({ request, env }));
    } catch (e) {
      console.error("api error:", e);
      res.writeHead(500, { "content-type": "application/json" });
      return res.end(JSON.stringify({ ok: false, error: "internal" }));
    }
    res.writeHead(404, { "content-type": "application/json" });
    return res.end(JSON.stringify({ ok: false, error: "not_found" }));
  }

  handleStatic(req, res, url);
});

server.listen(PORT, () => {
  console.log(`SayCue dev: http://127.0.0.1:${PORT}/`);
  console.log("  /api/events    → collector (lokalnie bez D1: 204, nic nie zapisuje)");
  console.log("  /api/subscribe → zapis e-maili (lokalnie bez D1: 503)");
  console.log("  /privacy       → informacja o prywatności");
});
