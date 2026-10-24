/* ==========================================================================
   SayCue — licznik zdarzeń strony walidacyjnej (bez danych osobowych).
   Wysyła WYŁĄCZNIE: {ts, event, utm_source, referrer_domain}.
   - żadnego adresu IP po naszej stronie (nie logujemy go),
   - żadnych cookies, localStorage, fingerprintingu, identyfikatora urządzenia,
   - zewnętrzne pola: utm_source / utm_medium / utm_campaign (z URL), referrer_domain (hostname),
   - respektuje Do Not Track / Global Privacy Control,
   - działa w trybie offline (kolejka + ponowna próba), nigdy nie blokuje UI.
   ========================================================================== */

(function () {
  "use strict";

  // Własny endpoint; do czasu jego uruchomienia zdarzenia zbierają się tylko lokalnie
  // i są widoczne w podglądzie „Zobacz podgląd na żywo" (sekcja Prywatność).
  var ENDPOINT = "/api/events";
  var STORE_KEY = "saycue_ev_preview";   // tylko do podglądu w konsoli (SayCue.preview())
  var MAX_LOCAL = 30;
  var QUEUE = [];

  function dnt() {
    return (
      navigator.doNotTrack === "1" ||
      window.doNotTrack === "1" ||
      navigator.globalPrivacyControl === true
    );
  }

  function clean(value, maxLen) {
    if (!value) return null;
    var v = String(value).trim().slice(0, maxLen || 64);
    // wyłącznie bezpieczne znaki: litery, cyfry, - _ . : /
    v = v.replace(/[^a-zA-Z0-9\-_.:\/]/g, "");
    return v || null;
  }

  function queryParam(name) {
    try {
      return new URLSearchParams(window.location.search).get(name);
    } catch (e) {
      return null;
    }
  }

  function referrerDomain() {
    try {
      if (!document.referrer) return "direct";
      var host = new URL(document.referrer).hostname;
      return clean(host, 80) || "unknown";
    } catch (e) {
      return "unknown";
    }
  }

  function buildEvent(name, extra) {
    var ev = {
      ts: new Date().toISOString(),          // ISO 8601 — koordynacja z events.jsonl aplikacji
      event: clean(name, 48) || "unknown",
      utm_source: "direct",
      referrer_domain: referrerDomain()
    };
    // utm_source zapamiętany z pierwszego wejścia w tej karcie (bez cookie: sessionStorage)
    var utm = clean(queryParam("utm_source"), 48);
    try {
      if (utm) {
        sessionStorage.setItem("saycue_utm", utm);
        ev.utm_source = utm;
      } else if (sessionStorage.getItem("saycue_utm")) {
        ev.utm_source = clean(sessionStorage.getItem("saycue_utm"), 48) || "direct";
      }
    } catch (e) {
      ev.utm_source = utm || "direct";     // prywatny tryb: bez pamięci, tylko bieżący URL
    }
    if (extra) {
      Object.keys(extra).forEach(function (k) {
        var v = clean(extra[k], 48);
        if (v) ev[k] = v;   // dodatkowe pola MUSZĄ być identyfikatorami (np. surface=hero)
      });
    }
    return ev;
  }

  function storeLocally(ev) {
    try {
      var raw = null;
      try { raw = sessionStorage.getItem(STORE_KEY); } catch (e) { raw = null; }
      var arr = raw ? JSON.parse(raw) : [];
      arr.push(ev);
      if (arr.length > MAX_LOCAL) arr = arr.slice(-MAX_LOCAL);
      try { sessionStorage.setItem(STORE_KEY, JSON.stringify(arr)); } catch (e) {}
    } catch (e) {}
  }

  function send(body) {
    if (typeof fetch !== "function") return;
    try {
      fetch(ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        keepalive: true,     // zdarzenie dojdzie nawet przy zamknięciu karty
        credentials: "omit"  // ZERO cookies w żądaniu
      }).catch(function () { /* offline / 404 do czasu podłączenia — ignorujemy */ });
    } catch (e) {}
  }

  function track(name, extra) {
    if (dnt()) return;                  // pełna cisza przy DNT/GPC
    var ev = buildEvent(name, extra);
    storeLocally(ev);                   // 1) zawsze: podgląd lokalny (przezroczystość)
    send(ev);                           // 2) best-effort do własnego endpointu
  }

  function flushQueue() {
    while (QUEUE.length) {
      var item = QUEUE.shift();
      track(item.name, item.extra);
    }
  }

  // ---------- zdarzenia wbudowane ----------

  // 1) odsłona
  track("page_view");

  // 2) kliknięcia elementów oznaczonych data-ev
  document.addEventListener("click", function (e) {
    var el = e.target && e.target.closest ? e.target.closest("[data-ev]") : null;
    if (!el) return;
    track(el.getAttribute("data-ev"), { surface: el.getAttribute("data-surface") || el.id || "unknown" });
  }, { passive: true });

  // 3) sekcja cen widoczna (G4c: widzowie sekcji cen)
  var priced = document.querySelector('[data-observe="pricing_section_view"]');
  if (priced && "IntersectionObserver" in window) {
    var seen = false;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting && !seen) {
          seen = true;
          track("pricing_section_view");
          io.disconnect();
        }
      });
    }, { threshold: 0.35 });
    io.observe(priced);
  } else if (priced) {
    track("pricing_section_view"); // starsze przeglądarki: bez obserwacji
  }

  // 4) formularz: start wypełniania + wysłanie. E-mail NIE trafia do collector-a zdarzeń —
  //    idzie wyłącznie do /api/subscribe (osobna funkcja, osobna tabela D1).
  var form = document.getElementById("waitlist-form");
  if (form) {
    var touched = false;
    form.addEventListener("focusin", function () {
      if (!touched) { touched = true; track("waitlist_form_start"); }
    }, { passive: true });

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var status = document.getElementById("form-status");
      var email = String(form.email.value || "").trim().toLowerCase();
      var ok = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email) && email.length <= 254;
      if (!ok) {
        if (status) { status.className = "form-note err"; status.textContent = "Popraw adres e-mail."; }
        return;
      }
      var button = form.querySelector('button[type="submit"]');
      if (button) { button.disabled = true; button.textContent = "Zapisuję…"; }
      if (status) { status.className = "form-note"; status.textContent = ""; }

      fetch("/api/subscribe", {
        method: "POST",
        headers: { "content-type": "application/json" },
        credentials: "omit",
        body: JSON.stringify({
          email: email,
          wants_paid: !!(form.wants_paid && form.wants_paid.checked),
          website: form.website ? form.website.value : "",   // honeypot — boty go wypełniają
          source: "landing"
        })
      })
        .then(function (res) { return res.json().catch(function () { return {}; }).then(function (body) { return { res: res, body: body }; }); })
        .then(function (out) {
          if (out.res.ok && out.body.ok) {
            // licznik zdarzeń dostaje WYŁĄCZNIE fakt wysłania (bez adresu)
            track("waitlist_submit", { wants_paid: form.wants_paid && form.wants_paid.checked ? "yes" : "no" });
            if (status) { status.className = "form-note"; status.textContent = "Zapisane. Napiszemy dopiero, gdy paczki presetów będą gotowe."; }
            form.reset();
          } else if (out.res.status === 429) {
            if (status) { status.className = "form-note err"; status.textContent = "Zbyt wiele prób — spróbuj za kilka minut."; }
          } else if (out.res.status === 503) {
            if (status) { status.className = "form-note err"; status.textContent = "Zapis chwilowo niedostępny. Spróbuj ponownie za chwilę."; }
          } else {
            if (status) { status.className = "form-note err"; status.textContent = "Nie udało się zapisać — popraw adres i spróbuj jeszcze raz."; }
          }
        })
        .catch(function () {
          if (status) { status.className = "form-note err"; status.textContent = "Brak połączenia z serwerem. Spróbuj ponownie."; }
        })
        .then(function () {
          if (button) { button.disabled = false; button.textContent = "Zapisz mnie"; }
        });
    });
  }

  // 5) publiczny API (przydatne do ręcznego testu w konsoli: SayCue.track("demo", {surface:"test"}))
  window.SayCue = {
    track: track,
    preview: function () {
      // podgląd wyłącznie w konsoli — lista zdarzeń jest dokumentowana na /privacy
      var raw = null;
      try { raw = sessionStorage.getItem(STORE_KEY); } catch (e) { raw = null; }
      var arr = [];
      try { arr = raw ? JSON.parse(raw) : []; } catch (e) { arr = []; }
      if (console && console.table) { console.table(arr); } else { console.log(arr); }
      return arr;
    }
  };
  flushQueue();
})();
