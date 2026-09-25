import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

/**
 * Guards the i18n sweep of bug report 083.
 *
 * Interface text lives in `src/lib/i18n/locales/*.json` and is read through `$t`; numbers and dates
 * are formatted with the active locale through `format` / `formatNumber` from the same module. Before
 * the sweep a few hundred strings were typed straight into components in Dutch and a dozen files
 * formatted with a hard-coded `'nl-NL'`, so an English interface showed Dutch confirm dialogs, Dutch
 * error messages and Dutch digit grouping. This scans the source for the phrases that were moved and
 * for the locale tag, so neither can come back unnoticed.
 *
 * Comments and `console.*` lines are skipped: they are read by developers, not listeners, and the
 * code comments here are allowed to quote the Dutch interface they describe.
 */

const SRC = join(process.cwd(), "src");

/**
 * Phrases that used to be hard-coded. Each is distinctive enough that it only ever appears as
 * interface text -- a match outside a comment is a string that belongs in the locale files.
 */
const DUTCH_PHRASES = [
  // Media session / player
  "Onbekend nummer",
  "Onbekende artiest",
  "Onbekend album",
  // Dialogs
  "Weet je zeker",
  "opnieuw wilt parsen",
  "Selecteer eerst een gebruiker",
  "Geef een naam voor",
  "opnieuw uitvoeren?",
  "opnieuw downloaden?",
  "terugzetten naar normaal tempo",
  // Buttons, titles, headings
  "Toevoegen aan favorieten",
  "Verwijderen uit favorieten",
  "Artiest bewerken",
  "Genre bewerken",
  "Label bewerken",
  "Alle Nummers",
  // Errors
  "Kon geen verbinding maken",
  "Toegangsaanvraag mislukt",
  "Fout bij indienen",
  "Setup mislukt",
  "Netwerkfout bij",
  "Server niet bereikbaar",
  "Opslaan is niet gelukt",
  "Opslaan mislukt",
  "Kon gegevens niet ophalen",
  "Kon gebruiker niet",
  "Kon gebruikers niet",
  "Kon wachtwoord niet",
  "Kon bibliotheek",
  "Kon bibliotheken",
  "Kon account niet",
  "Kon kanaal niet",
  "Kon scan",
  "Kon genres niet",
  "Kon toegangsverzoeken",
  "Kon bestand niet lezen",
  "Kopiëren is niet gelukt",
  "Sync mislukt",
  // Curation
  "Nog niet in de bibliotheek",
  "tracks in de bibliotheek",
  "in de wachtrij om opnieuw getagd",
  "Dat is geen MBID",
  "Nog geen regels",
  "Nog niet beoordeeld",
  "Geen subgenres",
  "Catalogus laden",
  "Nog geen beslissing",
  "Nog geen externe",
  "Wordt nooit getagd",
  "niet in zichzelf samengevoegd",
  "mag niet leeg zijn",
  // Management
  "Alle systemen werken",
  "Alleen-lezen",
  "Draaiende instellingen",
  "Pad alleen zichtbaar",
  "Geen artiesten gevonden",
  "Nog geen primaire",
  "Met afbeelding",
  "Zonder afbeelding",
  "hoort nu bij",
  "Kon de backoff niet",
  "Kon fetch taak niet",
  "nog niet geteld",
  "definitief mislukt",
];

/**
 * Every `.svelte` and `.js` file under `dir`, recursively, except the i18n module and its locales
 * (where the Dutch text is supposed to be).
 *
 * @param {string} dir
 * @returns {string[]}
 */
function sourceFiles(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return name === "i18n" ? [] : sourceFiles(path);
    return /\.(svelte|js)$/.test(name) ? [path] : [];
  });
}

/**
 * The source with comments and console lines blanked out, line count preserved.
 *
 * @param {string} text
 * @returns {string}
 */
function withoutComments(text) {
  const blank = (match) => match.replace(/[^\n]/g, " ");
  return text
    .replace(/<!--[\s\S]*?-->/g, blank)
    .replace(/\/\*[\s\S]*?\*\//g, blank)
    .replace(/(^|[^:"'`\\])\/\/[^\n]*/g, (match, lead) => lead + blank(match.slice(lead.length)))
    .replace(/^.*console\.[a-z]+\(.*$/gm, blank);
}

/**
 * Every `file:line: phrase` where one of `needles` occurs in code.
 *
 * @param {string[]} needles
 * @returns {string[]}
 */
function occurrences(needles) {
  return sourceFiles(SRC).flatMap((file) =>
    withoutComments(readFileSync(file, "utf8"))
      .split("\n")
      .flatMap((line, index) =>
        needles
          .filter((needle) => line.includes(needle))
          .map((needle) => `${relative(SRC, file)}:${index + 1}: ${needle}`),
      ),
  );
}

describe("no hard-coded Dutch interface text", () => {
  it("keeps the moved phrases in the locale files", () => {
    expect(occurrences(DUTCH_PHRASES)).toEqual([]);
  });

  it("formats numbers and dates with the active locale, never a fixed 'nl-NL'", () => {
    expect(occurrences(["nl-NL"])).toEqual([]);
  });

  it("strips comments without eating URLs in strings", () => {
    expect(withoutComments('const u = "https://x"; // Weet je zeker')).toContain("https://x");
    expect(withoutComments('const u = "https://x"; // Weet je zeker')).not.toContain("Weet je");
    expect(withoutComments("<!-- Onbekend nummer -->")).not.toContain("Onbekend");
  });
});
