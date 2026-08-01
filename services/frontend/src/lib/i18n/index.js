import { writable, derived, get } from "svelte/store";

/**
 * The languages the interface ships in, each labelled in its own language so
 * the picker stays readable no matter which locale is currently active.
 */
export const SUPPORTED_LOCALES = [
  { code: "en", label: "English" },
  { code: "nl", label: "Nederlands" },
];

export const DEFAULT_LOCALE = "en";

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

function lookup(dictionary, key) {
  const value = key
    .split(".")
    .reduce((node, part) => (node == null ? undefined : node[part]), dictionary);
  return typeof value === "string" ? value : undefined;
}

function interpolate(template, vars) {
  return template.replace(/\{(\w+)\}/g, (match, name) =>
    vars[name] === undefined ? match : String(vars[name]),
  );
}

/**
 * Builds the translation function for one locale.
 *
 * A key missing from the active locale falls back to English; missing there
 * too, the key itself is returned, so an untranslated string is always
 * recognisable rather than blank.
 *
 * @param {Record<string, object>} dictionaries - Locale code to translations.
 * @param {string} localeCode - The active locale.
 * @returns {function(string, Object=): string}
 */
export function createTranslator(dictionaries, localeCode) {
  return (key, vars) => {
    const value =
      lookup(dictionaries[localeCode], key) ?? lookup(dictionaries[DEFAULT_LOCALE], key);
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
    document.documentElement.lang = code;
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
