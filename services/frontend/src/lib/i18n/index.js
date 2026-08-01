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
 * Every translation file, loaded eagerly: there are only two of them and a
 * synchronous lookup keeps `t` free of "not loaded yet" states, both on first
 * paint and in unit tests. Revisit if the locale count grows materially.
 */
const DICTIONARIES = Object.fromEntries(
  Object.entries(import.meta.glob("./locales/*.json", { eager: true })).map(([path, module]) => [
    path.match(/([^/]+)\.json$/)[1],
    module.default,
  ]),
);

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
    localeStore.set(code);
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
  if (isSupported(code)) localeStore.set(code);
}

/**
 * Drops back to the language this browser resolves to on its own, used when
 * the account whose language was applied logs out.
 */
export function resetLocaleToBrowser() {
  localeStore.set(resolveInitialLocale());
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
export const t = derived(localeStore, ($locale) => createTranslator(DICTIONARIES, $locale));

/**
 * Reads the active locale outside of a component.
 * @returns {string}
 */
export function currentLocale() {
  return get(localeStore);
}
