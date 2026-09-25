/**
 * Pure logic behind the artist, label and genre edit pages.
 *
 * The same split the genre curation tab uses: what a field accepts, and what a list
 * of parents does when you add to it, lives here so it can be tested without mounting
 * a component. The components only render it.
 *
 * MuMa's premise is that you edit as little as possible. These pages are the two
 * exceptions -- making a connection (an MBID, an alias) and writing a rule -- so
 * everything here is about keeping those two honest, not about editing metadata.
 */
import { get } from "svelte/store";

import { t } from "../i18n/index.js";
import { normalizeGenre } from "../management/genreCuration";

/** MusicBrainz ids are 8-4-4-4-12 hex, printed in either case. */
const MBID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Platforms the external-id rows may name.
 *
 * `musicbrainz` is deliberately absent: the MBID field owns that row and writes it on
 * save, so a second input for the same source would let the page contradict itself.
 */
export const EXTERNAL_SOURCES = ["spotify", "soundcloud", "discogs", "beatport", "youtube"];

/**
 * Whether a field holds something storable as an MBID.
 *
 * Empty counts as valid: an empty field means "no id", which is a legitimate state and
 * is how an id gets cleared. Only a non-empty value that is not an MBID is an error --
 * most often a pasted MusicBrainz URL.
 *
 * @param {string|null|undefined} value
 * @returns {boolean}
 */
export function isMbid(value) {
  const candidate = (value || "").trim();
  if (!candidate) return true;
  return MBID_PATTERN.test(candidate);
}

/**
 * The MusicBrainz page for an id, so a curator can check what they just linked.
 *
 * @param {'artist'|'label'} kind
 * @param {string|null|undefined} mbid
 * @returns {string|null} The URL, or null when there is no id to link to.
 */
export function mbidUrl(kind, mbid) {
  const candidate = (mbid || "").trim();
  if (!candidate) return null;
  return `https://musicbrainz.org/${kind}/${candidate}`;
}

/**
 * Whether `parent` may be added to `subject`'s parent list.
 *
 * Compared on the normalized key rather than the raw string, so 'Hardcore' and
 * 'hard-core' are recognised as one genre -- the same rule the tagger applies.
 *
 * A genre below `subject` (any depth, from the page's `descendants`) is refused too:
 * filing a genre under its own subgenre closes a cycle, which the backend answers
 * with a 409 anyway -- refusing it here just saves the round trip.
 *
 * @param {string} subject - The genre being edited.
 * @param {string} parent - The candidate parent.
 * @param {string[]} current - Parents already on the list.
 * @param {string[]} [descendants] - Every genre below `subject`.
 * @returns {boolean}
 */
export function parentIsAllowed(subject, parent, current, descendants = []) {
  const key = normalizeGenre(parent);
  if (!key) return false;
  if (key === normalizeGenre(subject)) return false;
  if (descendants.some((below) => normalizeGenre(below) === key)) return false;
  return !current.some((existing) => normalizeGenre(existing) === key);
}

/**
 * The parent list with one more entry. Returns a new array.
 *
 * @param {string[]} current
 * @param {string} parent
 * @returns {string[]}
 */
export function addParent(current, parent) {
  return [...current, parent.trim()];
}

/**
 * The parent list without the named entry, matched the way the tagger matches.
 *
 * @param {string[]} current
 * @param {string} parent
 * @returns {string[]}
 */
export function removeParent(current, parent) {
  const key = normalizeGenre(parent);
  return current.filter((existing) => normalizeGenre(existing) !== key);
}

/**
 * How a rule's reach reads next to the Apply button.
 *
 * @param {number} count
 * @returns {string}
 */
export function affectedLabel(count) {
  if (!count) return get(t)("curation.affectedNone");
  return get(t)("curation.affectedTracks", { count });
}

/**
 * Whether a genre has anything to edit.
 *
 * Curation answers whether a genre exists; this page answers what else is true about
 * one that does. A rejected or still-undecided genre is not part of the library, so
 * its hierarchy is not editable and the pencil is not offered.
 *
 * @param {{state?: string}|null|undefined} genre
 * @returns {boolean}
 */
export function canEditGenre(genre) {
  return (genre || {}).state === "white";
}

/**
 * Whether a value is storable as a genre's hardness: a whole number 0-100, or
 * empty/null to clear it back to "not scored".
 *
 * The daily mixes bucket a track by this number (soft/mid/hard), so a value outside
 * 0-100 is not a typo to shrug off -- the backend refuses it too
 * (`curation_rules.parse_hardness`), and this is the same rule stated where the form
 * can check it before a round trip.
 *
 * @param {string|number|null|undefined} value
 * @returns {boolean}
 */
export function isHardness(value) {
  if (value === null || value === undefined || value === "") return true;
  const number = Number(value);
  return Number.isInteger(number) && number >= 0 && number <= 100;
}

/**
 * `isHardness`'s value, parsed into what the API expects: an integer, or null for
 * "not scored". Assumes `isHardness(value)` already returned true.
 *
 * @param {string|number|null|undefined} value
 * @returns {number|null}
 */
export function parseHardness(value) {
  if (value === null || value === undefined || value === "") return null;
  return Number(value);
}
