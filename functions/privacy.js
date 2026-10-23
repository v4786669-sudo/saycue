/**
 * SayCue — strona prywatności (/privacy). Statyczny HTML w Functions = brak duplikatu
 * treści poza index (stopka landingu linkuje do /privacy).
 *
 * Renderowany z jednego źródła prawdy o tym, co zbieramy — patrz _shared/events.js
 * i _shared/subscribe.js. Jeśli zmienisz zbierane pola, zaktualizuj tę stronę (test
 * w scripts/test-functions.mjs pilnuje, że lista zdarzeń jest wymieniona).
 */

const EVENTS = [
  ["page_view", "wejście na stronę"],
  ["download_click", "klik przycisku „Pobierz”"],
  ["github_click / discord_click", "klik linku do GitHub-a lub Discorda"],
  ["gif_placeholder_click", "klik w miejsce demo"],
  ["pricing_section_view", "przewinięcie do sekcji cen"],
  ["waitlist_form_start", "zaczęcie wypełniania formularza"],
  ["waitlist_submit", "wysłanie formularza (tylko fakt, bez treści)"],
];

export function onRequestGet() {
  const rows = EVENTS.map(([name, desc]) => `<tr><td><code>${name}</code></td><td>${desc}</td></tr>`).join("");
  const html = `<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prywatność — SayCue</title>
<link rel="stylesheet" href="/assets/style.css">
<meta name="robots" content="noindex">
</head><body>
<main id="main">
<section class="section"><div class="wrap narrow">
<h1>Prywatność — na piśmie</h1>
<p class="lede small">SayCue to lokalny asystent głosowy. Ta strona jest stroną walidacyjną: zbiera wyłącznie anonimowe liczniki i e-maile na życzenie.</p>

<h2>Co zbieramy (i czego nie zbieramy)</h2>
<table class="truth"><tbody>${rows}</tbody></table>
<p>Każde zdarzenie to <strong>wyłącznie</strong> <code>{ts, event, utm_source, referrer_domain}</code> — bez adresu IP, bez cookies, bez identyfikatora urządzenia, bez treści, które wpisujesz.</p>

<h2>Formularz e-mail</h2>
<ul>
  <li><strong>Po co:</strong> jednorazowo powiadomić Cię o publikacji paczek presetów i bet. Nic więcej.</li>
  <li><strong>Gdzie trafia:</strong> wyłącznie do naszej bazy (Cloudflare D1). <strong>Nie</strong> do licznika zdarzeń.</li>
  <li><strong>Jak długo:</strong> 12 miesięcy albo do usunięcia na Twoją prośbę — wtedy też od razu.</li>
  <li><strong>Komu przekazujemy:</strong> nikomu. Zero osób trzecich, zero profilowania, brak marketingu.</li>
  <li><strong>Usunięcie:</strong> napisz na <a href="mailto:privacy@saycue.example">privacy@saycue.example</a> z tematem „USUŃ”.</li>
</ul>

<h2>Do Not Track / Global Privacy Control</h2>
<p>Jeśli Twoja przeglądarka wysyła sygnał DNT albo GPC, strona <strong>nie zapisuje żadnych zdarzeń</strong>.</p>

<h2>Aplikacja (SayCue na Twoim komputerze)</h2>
<p>Rozpoznawanie mowy działa lokalnie. Aplikacja nie wysyła audio. Statystyki są zapisywane u Ciebie i wysyłane tylko wtedy, gdy sam klikniesz „wyślij raport”. <a href="/">Wróć na stronę główną</a>.</p>
</div></section>
</main></body></html>`;
  return new Response(html, {
    headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" },
  });
}
