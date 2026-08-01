import { describe, it, expect, beforeEach } from "vitest";
import { get } from "svelte/store";
import {
  createTranslator,
  resolveInitialLocale,
  locale,
  setLocaleFromAccount,
  t,
  SUPPORTED_LOCALES,
  DEFAULT_LOCALE,
} from "../../src/lib/i18n";

const DICTS = {
  en: {
    settings: { language: { title: "Language" } },
    greeting: "Hi {name}",
    onlyEnglish: "English only",
    branch: { nested: "value" },
  },
  nl: {
    settings: { language: { title: "Taal" } },
    greeting: "Hoi {name}",
    branch: { nested: "waarde" },
  },
};

describe("i18n - createTranslator", () => {
  it("resolves a nested key from the active dictionary", () => {
    const translate = createTranslator(DICTS, "nl");
    expect(translate("settings.language.title")).toBe("Taal");
  });

  it("falls back to English when the key is missing in the active locale", () => {
    const translate = createTranslator(DICTS, "nl");
    expect(translate("onlyEnglish")).toBe("English only");
  });

  it("returns the key itself when it is missing from every dictionary", () => {
    const translate = createTranslator(DICTS, "nl");
    expect(translate("does.not.exist")).toBe("does.not.exist");
  });

  it("returns the key itself when the key resolves to an object rather than a string", () => {
    const translate = createTranslator(DICTS, "nl");
    expect(translate("branch")).toBe("branch");
  });

  it("interpolates named placeholders", () => {
    const translate = createTranslator(DICTS, "nl");
    expect(translate("greeting", { name: "Teun" })).toBe("Hoi Teun");
  });

  it("leaves a placeholder verbatim when no matching variable is given", () => {
    const translate = createTranslator(DICTS, "en");
    expect(translate("greeting")).toBe("Hi {name}");
  });

  it("falls back to English for an unknown locale", () => {
    const translate = createTranslator(DICTS, "fr");
    expect(translate("settings.language.title")).toBe("Language");
  });
});

describe("i18n - resolveInitialLocale", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("prefers a supported locale stored in localStorage", () => {
    localStorage.setItem("muma_locale", JSON.stringify("nl"));
    expect(resolveInitialLocale("en-US")).toBe("nl");
  });

  it("ignores an unsupported stored locale and uses the browser language", () => {
    localStorage.setItem("muma_locale", JSON.stringify("fr"));
    expect(resolveInitialLocale("nl-BE")).toBe("nl");
  });

  it("uses the primary subtag of the browser language", () => {
    expect(resolveInitialLocale("nl-NL")).toBe("nl");
  });

  it("falls back to the default locale for an unsupported browser language", () => {
    expect(resolveInitialLocale("fr-FR")).toBe(DEFAULT_LOCALE);
  });

  it("falls back to the default locale when the browser reports no language", () => {
    expect(resolveInitialLocale(undefined)).toBe(DEFAULT_LOCALE);
  });
});

describe("i18n - locale store", () => {
  beforeEach(() => {
    locale.set(DEFAULT_LOCALE);
  });

  it("ships English and Dutch, each labelled in its own language", () => {
    expect(SUPPORTED_LOCALES).toEqual([
      { code: "en", label: "English" },
      { code: "nl", label: "Nederlands" },
    ]);
  });

  it("keeps the previous locale when set to an unsupported code", () => {
    locale.set("nl");
    locale.set("fr");
    expect(get(locale)).toBe("nl");
  });

  it("persists the chosen locale to localStorage", () => {
    locale.set("nl");
    expect(JSON.parse(localStorage.getItem("muma_locale"))).toBe("nl");
  });

  it("mirrors the chosen locale onto the document language", () => {
    locale.set("nl");
    expect(document.documentElement.lang).toBe("nl");
  });
});

describe("i18n - setLocaleFromAccount", () => {
  beforeEach(() => {
    localStorage.clear();
    locale.set(DEFAULT_LOCALE);
  });

  it("applies a language coming from the account", () => {
    setLocaleFromAccount("nl");
    expect(get(locale)).toBe("nl");
  });

  it("does not overwrite this browser's own stored preference", () => {
    localStorage.setItem("muma_locale", JSON.stringify("en"));
    setLocaleFromAccount("nl");
    expect(JSON.parse(localStorage.getItem("muma_locale"))).toBe("en");
  });

  it("ignores an unsupported language stored on the account", () => {
    locale.set("nl");
    setLocaleFromAccount("fr");
    expect(get(locale)).toBe("nl");
  });
});

describe("i18n - t store", () => {
  beforeEach(() => {
    locale.set(DEFAULT_LOCALE);
  });

  it("translates a shipped key in English", () => {
    expect(get(t)("settings.language.title")).toBe("Language");
  });

  it("translates the same key in Dutch after switching locale", () => {
    locale.set("nl");
    expect(get(t)("settings.language.title")).toBe("Taal");
  });
});
