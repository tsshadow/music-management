/**
 * The in-app manual: one section per thing a listener can do, each with the
 * place it lives so the reader can go and try it.
 *
 * The text itself is in the locale files under `help.<id>` (`title` and `body`,
 * the body as paragraphs separated by a blank line), so the manual reads in the
 * interface language like everything else. What lives here is the *shape*: the
 * order, which view a section opens, and which sections only apply inside the
 * phone shell (`native`) or to an administrator (`admin`). `Help.svelte` renders
 * the list; the setup tour's last step points at it.
 *
 * @typedef {Object} HelpSection
 * @property {string} id - Also the locale key under `help.`.
 * @property {string} [view] - The view `onnavigate` opens for "go there".
 * @property {boolean} [native] - Only inside the phone shell.
 * @property {boolean} [admin] - Only for administrators.
 */

/** @type {HelpSection[]} */
export const HELP_SECTIONS = [
  { id: "home", view: "home" },
  { id: "mode" },
  { id: "browse", view: "genres" },
  { id: "search", view: "new-preset" },
  { id: "favorites", view: "favorites" },
  { id: "feeds", view: "daily-mixes" },
  { id: "memories", view: "memories" },
  { id: "stats", view: "listening" },
  { id: "queue" },
  { id: "downloads", view: "downloads", native: true },
  { id: "car", view: "car", native: true },
  { id: "voice", view: "voice", native: true },
  { id: "settings" },
  { id: "management", view: "management", admin: true },
];

/**
 * The sections that apply to this reader.
 *
 * @param {{native?: boolean, admin?: boolean}} reader
 * @returns {HelpSection[]}
 */
export function sectionsFor({ native = false, admin = false } = {}) {
  return HELP_SECTIONS.filter(
    (section) => (!section.native || native) && (!section.admin || admin),
  );
}

/**
 * Splits a section body into its paragraphs. The locale files keep a body as
 * one string with blank lines between paragraphs, which reads naturally in the
 * JSON and keeps the key count down; this is the one place that shape is known.
 *
 * @param {string} body
 * @returns {string[]}
 */
export function paragraphsOf(body) {
  return String(body ?? "")
    .split(/\n\s*\n/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);
}
