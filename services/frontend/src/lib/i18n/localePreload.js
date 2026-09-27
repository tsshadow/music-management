/**
 * A `<link rel="modulepreload">` for the locale file the app is about to ask for (issue #118).
 *
 * Each locale is its own chunk (`index.js`, issue #114), and `main.js` only asks for it once the
 * entry has been fetched, parsed and run -- one round trip after the entry, behind the boot
 * screen, in a browser. The build knows every locale's hashed file name and the page knows the
 * listener's locale before any module runs, so `vite.config.js` (`localePreload` plugin) writes a
 * small inline script into `index.html` that starts that file together with the entry.
 *
 * Nothing here is imported by the app: the plugin inlines `preloadLocaleFiles` by its source,
 * with the plan from `localePreloadPlan` as its argument. Neither may therefore use anything from
 * outside its own body.
 */

/**
 * The files a locale cannot be shown without, as `requiredLocales` in `index.js` answers it:
 * a dialect needs Dutch too, English and Dutch only themselves. Duplicated because the build
 * cannot import `index.js` (it pulls in Svelte stores and `import.meta.glob`);
 * `tests/unit/localePreload.test.js` keeps the two in step.
 */
export const LOCALE_PRELOAD_CHAINS = {
  sallands: ["sallands", "nl"],
  brabants: ["brabants", "nl"],
};

/**
 * Locale code to the URLs of the files it needs, from the build's locale chunks.
 *
 * @param {Record<string, string>} files - Locale code to its chunk URL (`/assets/nl-xxxx.js`).
 * @returns {Record<string, string[]>}
 */
export function localePreloadPlan(files) {
  const plan = {};
  for (const code of Object.keys(files)) {
    const chain = LOCALE_PRELOAD_CHAINS[code] ?? [code];
    plan[code] = chain.filter((needed) => files[needed]).map((needed) => files[needed]);
  }
  return plan;
}

/**
 * Adds a modulepreload link for each file the starting locale needs. The locale is chosen the
 * way `resolveInitialLocale` in `index.js` chooses it: this browser's stored choice
 * (`muma_locale`), else its language when there is a file for it, else English. Never throws:
 * a missing preload only costs the round trip it was meant to save.
 *
 * @param {Window} win
 * @param {Record<string, string[]>} plan - What `localePreloadPlan` returned.
 */
export function preloadLocaleFiles(win, plan) {
  try {
    // Not `Object.hasOwn`: an older Android WebView lacks it, and this runs before any polyfill.
    const known = (key) => Object.prototype.hasOwnProperty.call(plan, key);
    let code = null;
    try {
      const stored = JSON.parse(win.localStorage.getItem("muma_locale") || "null");
      if (typeof stored === "string" && known(stored)) code = stored;
    } catch {
      // A corrupted stored value: fall through to the browser language, as the app does.
    }
    if (!code) {
      const primary = String((win.navigator && win.navigator.language) || "").split("-")[0];
      code = known(primary) ? primary : "en";
    }
    const doc = win.document;
    for (const href of plan[code] || []) {
      const link = doc.createElement("link");
      link.rel = "modulepreload";
      link.crossOrigin = "";
      link.href = href;
      doc.head.appendChild(link);
    }
  } catch {
    // See above: an optimisation, never a reason for the page not to start.
  }
}
