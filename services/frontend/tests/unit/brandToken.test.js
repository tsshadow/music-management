import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

/**
 * Guards the brand colour of sets mode.
 *
 * `bg-brand`, `text-brand` and friends are Tailwind utilities generated from the `--color-brand`
 * theme token in `src/app.css`, which follows `--brand-color` -- green for songs, blue under
 * `:root.mode-sets`. Tailwind v4 puts its utilities in `@layer utilities`, and an unlayered rule
 * always beats a layered one regardless of specificity. So a single component declaring
 * `:global(.bg-brand) { background-color: #1DB954 }` -- two did, both in the main bundle -- turned
 * every brand-coloured element in the app green, in sets mode too. jsdom does not run Tailwind, so
 * the computed colour cannot be asserted here; the rule that caused it can.
 */

const SRC = join(process.cwd(), "src");

/**
 * Every `.svelte` file under `dir`, recursively.
 *
 * @param {string} dir
 * @returns {string[]}
 */
function svelteFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return svelteFiles(path);
    return name.endsWith(".svelte") ? [path] : [];
  });
}

describe("brand colour token", () => {
  it("no component overrides a brand utility with a global rule", () => {
    const offenders = svelteFiles(SRC).filter((file) =>
      /:global\([^)]*-brand\b[^)]*\)/.test(readFileSync(file, "utf8")),
    );
    expect(offenders.map((file) => relative(SRC, file))).toEqual([]);
  });

  it("the theme token follows the mode, blue in sets mode", () => {
    const css = readFileSync(join(SRC, "app.css"), "utf8");
    expect(css).toMatch(/--color-brand:\s*var\(--brand-color/);
    expect(css).toMatch(/:root\.mode-sets\s*\{\s*--brand-color:\s*#2d5afc/);
  });
});
