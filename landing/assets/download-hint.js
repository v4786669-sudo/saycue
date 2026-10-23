/* SayCue — uczciwy stan przycisku pobierania.
   Jeśli release nie istnieje jeszcze (przed W4), przycisk prowadzi do formularza
   zamiast do martwego linku 404. Sprawdzamy raz, bez zewnętrznych bibliotek. */
(function () {
  "use strict";
  var link = document.querySelector("[data-download-link]");
  if (!link || typeof fetch !== "function") return;

  var target = link.getAttribute("href") || "";
  // GitHub: /releases → przekieruje na /releases/latest (200) albo na listę (200). Sprawdzamy
  // istnienie konkretnego pliku instalatora dopiero po publikacji — tu wystarcza HEAD na /releases.
  fetch(target, { method: "HEAD", redirect: "follow", cache: "no-store" })
    .then(function (res) {
      var hasRelease = res.ok && !/\/releases$/.test(res.url || "");
      if (!hasRelease) markPending(link);
    })
    .catch(function () { markPending(link); });

  function markPending(el) {
    el.setAttribute("href", "#waitlist");
    el.removeAttribute("rel");
    el.textContent = "Powiadom mnie o wydaniu";
    el.setAttribute("title", "Build v0.1.0 pojawi się na GitHubie w tygodniu 4. Zostaw e-mail, dostaniesz jeden sygnał.");
  }
})();
