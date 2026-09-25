import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { compile } from "tailwindcss";

/**
 * Guards that every theme-token colour class in `src/` compiles to a CSS rule.
 *
 * Tailwind v4 drops a class it cannot resolve without a word -- an undeclared `@theme` token, a
 * misspelt one, or a v3-only utility compiles to nothing and the element silently loses its colour.
 * MR !982 rewrote ~820 arbitrary colour classes onto `muma-spotify-*` tokens by script, which is
 * exactly the kind of change that would hide such a class; bug report 090 checked the rewrite and
 * found it clean, and this test keeps it that way. jsdom does not run Tailwind, so the stylesheet is
 * compiled here with Tailwind's own compiler against the real `src/app.css`.
 */

const ROOT = process.cwd();
const SRC = join(ROOT, "src");
const require = createRequire(join(ROOT, "package.json"));

/**
 * Every `.svelte` and `.js` file under `dir`, recursively.
 *
 * @param {string} dir
 * @returns {string[]}
 */
function sourceFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(svelte|js)$/.test(name) ? [path] : [];
  });
}

/**
 * The `--color-*` token names declared in `src/app.css`'s `@theme`.
 *
 * @param {string} css
 * @returns {string[]}
 */
function themeColorTokens(css) {
  const theme = css.match(/@theme\s*{([^}]*)}/)?.[1] ?? "";
  return [...theme.matchAll(/--color-([a-z0-9-]+)\s*:/g)].map((match) => match[1]);
}

/**
 * The CSS selector Tailwind emits for a class: every character outside `[A-Za-z0-9_-]` escaped.
 *
 * @param {string} cls
 * @returns {string}
 */
function selectorFor(cls) {
  return "." + cls.replace(/[^a-zA-Z0-9_-]/g, (char) => "\\" + char);
}

describe("theme token classes", () => {
  it("every class that uses a theme colour token produces a CSS rule", async () => {
    const appCss = readFileSync(join(SRC, "app.css"), "utf8");
    const tokens = themeColorTokens(appCss);
    expect(tokens).toContain("muma-spotify-dark");

    // A class is a run of utility characters that starts after whitespace, a quote, a backtick
    // or a brace, and ends in `-<token>` with an optional `/<opacity>`.
    const tokenAlternation = [...tokens].sort((a, b) => b.length - a.length).join("|");
    const classPattern = new RegExp(
      `(?<=[\\s"'\`{])[a-z!][a-z0-9:!-]*-(?:${tokenAlternation})(?:/\\d+)?(?![\\w/-])`,
      "g",
    );
    const classes = new Set();
    for (const file of sourceFiles(SRC)) {
      for (const match of readFileSync(file, "utf8").matchAll(classPattern)) classes.add(match[0]);
    }
    expect(classes.size).toBeGreaterThan(20);

    const compiler = await compile(appCss, {
      base: SRC,
      loadStylesheet: async (id, base) => {
        const path =
          id === "tailwindcss" ? require.resolve("tailwindcss/index.css") : join(base, id);
        return { path, base: dirname(path), content: readFileSync(path, "utf8") };
      },
    });
    const output = compiler.build([...classes]);

    const withoutRule = [...classes].filter((cls) => !output.includes(selectorFor(cls))).sort();
    expect(withoutRule).toEqual([]);
  });
});
