import { describe, it, expect } from "vitest";
import en from "../../src/lib/i18n/locales/en.json";
import nl from "../../src/lib/i18n/locales/nl.json";
import sallands from "../../src/lib/i18n/locales/sallands.json";
import brabants from "../../src/lib/i18n/locales/brabants.json";

/**
 * Flattens a nested translation file into the dotted keys components use, so
 * that two files can be compared as plain sets of strings.
 *
 * @param {object} node
 * @param {string} [prefix]
 * @returns {string[]}
 */
function keysOf(node, prefix = "") {
  return Object.entries(node).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof value === "string" ? [path] : keysOf(value, path);
  });
}

describe("locale files", () => {
  it("translates every English key into Dutch", () => {
    expect(keysOf(nl).sort()).toEqual(keysOf(en).sort());
  });

  // The dialects are deliberately partial -- anything they leave out reads as
  // Dutch -- so they are only checked in the other direction, which is what
  // catches a typo in a key name rather than a deliberate omission.
  it.each([
    ["sallands", sallands],
    ["brabants", brabants],
  ])("uses no key in %s that does not exist in Dutch", (_name, dialect) => {
    const dutchKeys = new Set(keysOf(nl));
    expect(keysOf(dialect).filter((key) => !dutchKeys.has(key))).toEqual([]);
  });
});
