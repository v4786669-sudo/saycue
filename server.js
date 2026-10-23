/**
 * SayCue — lokalny serwer statyczny + collector (Node 18+, bez zależności).
 * Użycie: node server.js [port]   (domyślnie 8787)
 * Test: saycue/landing/collector/test.js
 *
 * Endpointy:
 *   GET  /            → index.html i pliki statyczne z saycue/landing
 *   POST /api/events  → collector (whitelist 4 pól, bez IP/cookies)
 *   GET  /api/events  → 405 (collector jest tylko zapisowy)
 */
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { handle } from "./landing/collector/worker.js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "landing");
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

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);

  if (url.pathname === "/api/events") {
    if (req.method === "OPTIONS") {
      res.writeHead(204, {
        "access-control-allow-methods": "POST, OPTIONS",
        "access-control-allow-headers": "content-type",
        "access-control-max-age": "86400",
      });
      return res.end();
    }
    // Mapowanie Node Request → Web Request (undici jest globalne od Node 18)
    const body = await new Promise((resolve) => {
      const chunks = [];
      req.on("data", (c) => chunks.push(c));
      req.on("end", () => resolve(Buffer.concat(chunks)));
    });
    const webReq = new Request(`http://localhost${url.pathname}`, {
      method: req.method,
      headers: { "content-type": req.headers["content-type"] || "application/json" },
      body: req.method === "POST" ? body : undefined,
    });
    const webRes = await handle(webReq, {});
    const headers = {};
    webRes.headers.forEach((v, k) => { headers[k] = v; });
    res.writeHead(webRes.status, headers);
    return res.end(await webRes.text());
  }

  // Statyki: normalizacja ścieżki, żeby nie wyjść poza ROOT (path traversal).
  const rel = url.pathname === "/" ? "index.html" : decodeURIComponent(url.pathname).replace(/^\/+/, "");
  const file = path.resolve(ROOT, rel);
  if (!file.startsWith(ROOT + path.sep)) {
    res.writeHead(403, { "content-type": "text/plain" });
    return res.end("forbidden");
  }

  fs.readFile(file, (err, data) => {
    if (err) {
      // 404 → strona główna (typowo dla nieistniejących anchorów)
      if (rel !== "index.html") {
        res.writeHead(404, { "content-type": "text/html; charset=utf-8" });
        return res.end("<!doctype html><meta charset=utf-8><title>404</title><p>Nie ma tu nic. <a href='/'>Wróć</a></p>");
      }
      res.writeHead(500, { "content-type": "text/plain" });
      return res.end("internal error");
    }
    res.writeHead(200, {
      "content-type": MIME[path.extname(file)] || "application/octet-stream",
      "cache-control": "no-store",
    });
    res.end(data);
  });
});

server.listen(PORT, () => {
  console.log(`SayCue landing (lokalnie): http://127.0.0.1:${PORT}/`);
  console.log(`Collector: POST http://127.0.0.1:${PORT}/api/events (whitelist 4 pól, bez IP/cookies)`);
});
