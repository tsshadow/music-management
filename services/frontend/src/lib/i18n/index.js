import { writable, derived, get } from "svelte/store";

/**
 * The languages the interface ships in, each labelled in its own language so
 * the picker stays readable no matter which locale is currently active.
 */
export const SUPPORTED_LOCALES = [
  { code: "en", label: "English" },
  { code: "nl", label: "Nederlands" },
  { code: "sallands", label: "Sallaands" },
  { code: "brabants", label: "Brabants" },
];

export const DEFAULT_LOCALE = "en";

/**
 * Where a locale looks for a key it does not have itself.
 *
 * The dialects go through Dutch rather than straight to English, which is what
 * lets their files stay partial: they translate the text worth translating and
 * everything else reads as ordinary Dutch, instead of half the screen
 * switching to English.
 */
const FALLBACK_CHAINS = {
  sallands: ["sallands", "nl", "en"],
  brabants: ["brabants", "nl", "en"],
};

function chainFor(localeCode) {
  return FALLBACK_CHAINS[localeCode] ?? [localeCode, DEFAULT_LOCALE];
}

/**
 * The BCP 47 tag to report to the browser for a locale. Neither dialect has
 * one, and `nl` is what makes screen readers and spell-check behave.
 *
 * @param {string} localeCode
 * @returns {string}
 */
export function documentLanguage(localeCode) {
  return FALLBACK_CHAINS[localeCode] ? "nl" : localeCode;
}

const STORAGE_KEY = "muma_locale";

/**
 * Every translation file, as a loader: each locale is its own chunk, and only the ones the
 * active locale needs are fetched (issue #114). They used to be imported eagerly, which put
 * all four files -- 190 kB, over a quarter of what the first screen loaded -- in front of every
 * start, while a listener only ever reads one of them.
 */
const LOADERS = Object.fromEntries(
  Object.entries(import.meta.glob("./locales/*.json", { import: "default" })).map(
    ([path, load]) => [path.match(/([^/]+)\.json$/)[1], load],
  ),
);

/** The dictionaries that have arrived, by locale code. A store so `t` re-renders on arrival. */
const dictionaries = writable({});
const inFlight = new Map();

/**
 * The dictionaries a locale cannot be shown without: its fallback chain minus the English at
 * its end. Dutch is complete (`tests/unit/localeFiles.test.js`), so a Dutch or dialect
 * listener never reads an English string and does not wait for the file; English is still
 * fetched right after, for the key a future change forgets to translate.
 *
 * @param {string} localeCode
 * @returns {string[]}
 */
export function requiredLocales(localeCode) {
  const chain = [...new Set(chainFor(localeCode))].filter((code) => LOADERS[code]);
  return chain.length > 1 ? chain.filter((code) => code !== DEFAULT_LOCALE) : chain;
}

/** Fetches one dictionary, once; a failure is forgotten so the next call tries again. */
function loadDictionary(code) {
  if (get(dictionaries)[code]) return Promise.resolve();
  if (!LOADERS[code]) return Promise.resolve();
  if (!inFlight.has(code)) {
    inFlight.set(
      code,
      LOADERS[code]().then(
        (dictionary) => {
          dictionaries.update((all) => ({ ...all, [code]: dictionary }));
          inFlight.delete(code);
        },
        (error) => {
          inFlight.delete(code);
          throw error;
        },
      ),
    );
  }
  return inFlight.get(code);
}

/**
 * Whether a locale can be shown right now.
 *
 * @param {string} localeCode
 * @returns {boolean}
 */
export function isLocaleLoaded(localeCode) {
  const loaded = get(dictionaries);
  return requiredLocales(localeCode).every((code) => loaded[code]);
}

/**
 * Fetches what a locale needs (`requiredLocales`), then the rest of its chain in the
 * background. Resolves once it can be shown; never rejects -- a locale whose file failed to
 * load falls back along its chain, and at worst shows the keys.
 *
 * @param {string} localeCode
 * @returns {Promise<void>}
 */
export function loadLocale(localeCode) {
  const required = requiredLocales(localeCode);
  const rest = chainFor(localeCode).filter((code) => !required.includes(code));
  return Promise.all(required.map((code) => loadDictionary(code).catch(() => null))).then(() => {
    for (const code of rest) loadDictionary(code).catch(() => null);
  });
}

/**
 * Fetches every locale. For the unit tests' setup file, which renders components in any
 * language without waiting; the app itself never needs all of them.
 *
 * @returns {Promise<void>}
 */
export function loadAllLocales() {
  return Promise.all(Object.keys(LOADERS).map((code) => loadDictionary(code))).then(
    () => undefined,
  );
}

function isSupported(code) {
  return SUPPORTED_LOCALES.some((l) => l.code === code);
}

function resolve(dictionary, key) {
  return key.split(".").reduce((node, part) => (node == null ? undefined : node[part]), dictionary);
}

const pluralRulesCache = new Map();

function pluralRules(localeCode) {
  // Neither dialect is a language tag Intl knows, and both count the way Dutch
  // does, so they borrow its rules.
  const tag = documentLanguage(localeCode);
  if (!pluralRulesCache.has(tag)) pluralRulesCache.set(tag, new Intl.PluralRules(tag));
  return pluralRulesCache.get(tag);
}

/**
 * The text for one key in one dictionary, or undefined if this dictionary does
 * not have it.
 *
 * A key may hold either a string or, when the text depends on a number, an
 * object of plural forms keyed by CLDR category ("one", "other", ...). The
 * category is chosen with the rules of the locale the text is written in, not
 * the locale that is active: a Dutch string reached by falling back out of a
 * dialect must still pluralise as Dutch.
 *
 * @param {object} dictionary
 * @param {string} key
 * @param {string} localeCode - The locale this dictionary holds.
 * @param {Object} [vars]
 * @returns {string|undefined}
 */
function lookup(dictionary, key, localeCode, vars) {
  const node = resolve(dictionary, key);
  if (typeof node === "string") return node;
  if (node && typeof node === "object" && typeof vars?.count === "number") {
    const form = node[pluralRules(localeCode).select(vars.count)] ?? node.other;
    if (typeof form === "string") return form;
  }
  return undefined;
}

function interpolate(template, vars) {
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    vars[name] === undefined ? match : String(vars[name]),
  );
}

/**
 * Builds the translation function for one locale.
 *
 * A key missing from the active locale falls back along that locale's chain
 * (see `FALLBACK_CHAINS`), ending at English; missing there too, the key
 * itself is returned, so an untranslated string is always recognisable rather
 * than blank.
 *
 * @param {Record<string, object>} dictionaries - Locale code to translations.
 * @param {string} localeCode - The active locale.
 * @returns {function(string, Object=): string}
 */
export function createTranslator(dictionaries, localeCode) {
  const chain = chainFor(localeCode);
  return (key, vars) => {
    let value;
    for (const code of chain) {
      if (!dictionaries[code]) continue;
      value = lookup(dictionaries[code], key, code, vars);
      if (value !== undefined) break;
    }
    if (value === undefined) {
      if (import.meta.env.DEV) {
        console.warn(`Missing translation for "${key}"`);
      }
      return key;
    }
    return vars ? interpolate(value, vars) : value;
  };
}

/**
 * The locale to start in, before the account (if any) has been consulted:
 * this browser's stored choice, else its language when we speak it, else
 * English.
 *
 * @param {string} [browserLanguage] - Defaults to `navigator.language`.
 * @returns {string}
 */
export function resolveInitialLocale(browserLanguage = globalThis.navigator?.language) {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (isSupported(stored)) return stored;
  } catch {
    // Corrupted value: fall through to the browser language.
  }
  const primarySubtag = (browserLanguage || "").split("-")[0];
  return isSupported(primarySubtag) ? primarySubtag : DEFAULT_LOCALE;
}

const localeStore = writable(resolveInitialLocale());

let switchSeq = 0;

/**
 * Switches the active locale once its dictionary is in: at once when it already is (every
 * switch after the first, and every unit test), otherwise after the fetch, so the interface
 * never shows keys in between. The last request wins when switches overlap.
 *
 * @param {string} code
 */
function switchTo(code) {
  const seq = ++switchSeq;
  if (isLocaleLoaded(code)) {
    localeStore.set(code);
    loadLocale(code);
    return;
  }
  loadLocale(code).then(() => {
    if (seq === switchSeq) localeStore.set(code);
  });
}

/**
 * Resolves once the locale the app starts in can be shown. `main.js` waits for it before it
 * mounts, behind the boot screen.
 *
 * @returns {Promise<void>}
 */
export function localeReady() {
  return loadLocale(get(localeStore));
}

/**
 * The active locale. Unsupported codes are ignored rather than applied, so a
 * stale account value or a corrupted stored one can never blank the
 * interface.
 */
export const locale = {
  subscribe: localeStore.subscribe,
  set(code) {
    if (!isSupported(code)) return;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(code));
    switchTo(code);
  },
};

/**
 * Applies a language that came from the logged-in user's account, without
 * touching this browser's own stored preference: on logout the browser
 * falls back to its own language rather than keeping the previous user's.
 *
 * @param {string} code
 */
export function setLocaleFromAccount(code) {
  if (isSupported(code)) switchTo(code);
}

/**
 * Drops back to the language this browser resolves to on its own, used when
 * the account whose language was applied logs out.
 */
export function resetLocaleToBrowser() {
  switchTo(resolveInitialLocale());
}

localeStore.subscribe((code) => {
  if (typeof document !== "undefined") {
    document.documentElement.lang = documentLanguage(code);
  }
});

/**
 * Translation function for the active locale, as a store, so components
 * written as `{$t('some.key')}` re-render when the language changes.
 */
export const t = derived([localeStore, dictionaries], ([$locale, $dictionaries]) =>
  createTranslator($dictionaries, $locale),
);

/**
 * Reads the active locale outside of a component.
 * @returns {string}
 */
export function currentLocale() {
  return get(localeStore);
}

/**
 * Parses what the API sends as a timestamp. MariaDB's `YYYY-MM-DD HH:MM:SS`
 * has a space where ISO 8601 wants a `T`, which some engines refuse.
 *
 * @param {string|number|Date} value
 * @returns {Date}
 */
function toDate(value) {
  if (value instanceof Date || typeof value === "number") return new Date(value);
  return new Date(String(value).replace(" ", "T"));
}

/**
 * Formats a number the way the given locale groups digits (1,234 / 1.234).
 * `null`/`undefined` count as 0, which is what every counter in the UI wants.
 *
 * @param {number|string|null|undefined} value
 * @param {string} [localeCode] - Defaults to the active locale.
 * @returns {string}
 */
export function formatNumber(value, localeCode = currentLocale()) {
  return Number(value ?? 0).toLocaleString(documentLanguage(localeCode));
}

/**
 * Formats the date part of a timestamp in the given locale.
 *
 * @param {string|number|Date} value
 * @param {string} [localeCode] - Defaults to the active locale.
 * @returns {string}
 */
export function formatDate(value, localeCode = currentLocale()) {
  return toDate(value).toLocaleDateString(documentLanguage(localeCode));
}

/**
 * Formats a timestamp, date and time, in the given locale.
 *
 * @param {string|number|Date} value
 * @param {string} [localeCode] - Defaults to the active locale.
 * @returns {string}
 */
export function formatDateTime(value, localeCode = currentLocale()) {
  return toDate(value).toLocaleString(documentLanguage(localeCode));
}

/**
 * The formatters bound to the active locale, as a store, so a template written
 * as `{$format.number(count)}` re-renders when the language changes -- the
 * same reason `t` is a store. Never hard-code `'nl-NL'`: an English interface
 * then shows Dutch digit grouping (`tests/unit/noHardcodedDutch.test.js`).
 */
export const format = derived(localeStore, ($locale) => ({
  number: (value) => formatNumber(value, $locale),
  date: (value) => formatDate(value, $locale),
  dateTime: (value) => formatDateTime(value, $locale),
}));
