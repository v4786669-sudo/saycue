/**
 * SayCue — build katalogu publikacji (`public/`) z `landing/`.
 * Uruchomienie: node scripts/build-site.mjs   (albo: make site)
 *
 * Bezwzględne zasady (PLAN.md §4):
 *   - zero zewnętrznych zależności,
 *   - build ma być deterministyczny i szybki (< 1 s),
 *   - nie kopiujemy `collector/` (testy i README nie są potrzebne publicznie) ani `.git`.
 */
import { cp, mkdir, readdir, rm, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SRC = path.join(ROOT, "landing");
const OUT = path.join(ROOT, "public");

const SKIP_DIRS = new Set(["collector", "node_modules", ".git"]);
const SKIP_FILES = new Set(["README.md", "DEMO-GIF-SPEC.md"]);

async function copy(src, out) {
  await mkdir(out, { recursive: true });
  for (const entry of await readdir(src, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      await copy(path.join(src, entry.name), path.join(out, entry.name));
    } else {
      if (SKIP_FILES.has(entry.name)) continue;
      await cp(path.join(src, entry.name), path.join(out, entry.name));
    }
  }
}

async function main() {
  const t0 = Date.now();
  // Nie usuwamy README.md z public/ (dokumentacja katalogu publikacji zostaje).
  await rm(path.join(OUT, "assets"), { recursive: true, force: true });
  await rm(path.join(OUT, "index.html"), { force: true });
  await copy(SRC, OUT);
  // sanity: lokalny build musi zawierać index.html
  const st = await stat(path.join(OUT, "index.html"));
  if (!st.isFile() || st.size < 5000) {
    throw new Error("build: public/index.html nie wygląda na poprawny");
  }
  console.log(`build-site: landing/ → public/ (${Date.now() - t0} ms)`);
  console.log("  index.html, assets/* — bez landing/collector/*");
}

main().catch((err) => {
  console.error("build-site FAILED:", err.message);
  process.exit(1);
});
