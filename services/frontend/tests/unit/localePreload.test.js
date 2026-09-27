// The modulepreload hint for the starting locale's file (issue #118): the plugin in vite.config.js
// inlines `preloadLocaleFiles` into index.html with the plan from `localePreloadPlan`.
import { describe, it, expect, beforeEach } from "vitest";
import {
  LOCALE_PRELOAD_CHAINS,
  localePreloadPlan,
  preloadLocaleFiles,
} from "../../src/lib/i18n/localePreload.js";
import { SUPPORTED_LOCALES, requiredLocales } from "../../src/lib/i18n/index.js";

const FILES = Object.fromEntries(
  SUPPORTED_LOCALES.map(({ code }) => [code, `/assets/${code}-hash.js`]),
);

/** A window with its own document, storage and language, as the inline script sees it. */
function fakeWindow({ stored = null, language = "nl-NL" } = {}) {
  const doc = document.implementation.createHTMLDocument("boot");
  return {
    document: doc,
    navigator: { language },
    localStorage: { getItem: () => stored },
  };
}

/** The hrefs of the modulepreload links in a document. */
function preloaded(doc) {
  return [...doc.head.querySelectorAll('link[rel="modulepreload"]')].map((link) =>
    link.getAttribute("href"),
  );
}

describe("localePreload", () => {
  let plan;
  beforeEach(() => {
    plan = localePreloadPlan(FILES);
  });

  it("preloads exactly the files the app waits for, for every locale", () => {
    for (const { code } of SUPPORTED_LOCALES) {
      expect(plan[code]).toEqual(requiredLocales(code).map((needed) => FILES[needed]));
    }
    // Only the dialects need a second file.
    expect(Object.keys(LOCALE_PRELOAD_CHAINS).sort()).toEqual(["brabants", "sallands"]);
  });

  it("follows the stored choice first", () => {
    const win = fakeWindow({ stored: JSON.stringify("sallands"), language: "en-US" });

    preloadLocaleFiles(win, plan);

    expect(preloaded(win.document)).toEqual(["/assets/sallands-hash.js", "/assets/nl-hash.js"]);
    const link = win.document.head.querySelector("link");
    expect(link.getAttribute("crossorigin")).toBe("");
  });

  it("falls back to the browser language, then to English", () => {
    const dutch = fakeWindow({ language: "nl-BE" });
    preloadLocaleFiles(dutch, plan);
    expect(preloaded(dutch.document)).toEqual(["/assets/nl-hash.js"]);

    const german = fakeWindow({ language: "de-DE" });
    preloadLocaleFiles(german, plan);
    expect(preloaded(german.document)).toEqual(["/assets/en-hash.js"]);
  });

  it("ignores a corrupted or unsupported stored value, like the app does", () => {
    const corrupted = fakeWindow({ stored: "{not json", language: "nl" });
    preloadLocaleFiles(corrupted, plan);
    expect(preloaded(corrupted.document)).toEqual(["/assets/nl-hash.js"]);

    const unsupported = fakeWindow({ stored: JSON.stringify("fr"), language: "en" });
    preloadLocaleFiles(unsupported, plan);
    expect(preloaded(unsupported.document)).toEqual(["/assets/en-hash.js"]);
  });

  it("never throws, whatever the page lacks", () => {
    expect(() => preloadLocaleFiles({}, plan)).not.toThrow();
  });

  it("runs from its own source text, the way the plugin inlines it", () => {
    const win = fakeWindow({ stored: JSON.stringify("nl") });
    // Exactly what index.html does with the inlined text.
    const inlined = new Function(
      "window",
      `(${preloadLocaleFiles.toString()})(window, ${JSON.stringify(plan)});`,
    );

    inlined(win);

    expect(preloaded(win.document)).toEqual(["/assets/nl-hash.js"]);
  });
});
