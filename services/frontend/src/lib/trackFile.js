/**
 * The file behind a track, as the details sheet prints it.
 *
 * LMS already sends everything here on every song node -- `path`, `suffix`,
 * `bitRate`, `samplingRate`, `bitDepth`, `channelCount`, `size`, `created` --
 * the sheet just used to throw most of it away behind a "technical" toggle
 * that only showed the bitrate and the path. Pure functions so the formatting
 * is testable without rendering the sheet.
 */
import { formatBytes } from "./downloads.js";
import { formatBpm } from "./bpmFormat.js";

/** The last segment of a library path: what a listener recognises as "the file". */
export function fileName(path) {
  if (!path) return "";
  const parts = String(path).split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : "";
}

/** The path without its file name, or an empty string for a file at the root. */
export function folderOf(path) {
  if (!path) return "";
  const parts = String(path).split("/").filter(Boolean);
  return parts.slice(0, -1).join("/");
}

/**
 * `MP3 · 320 kbps · 44,1 kHz · 16 bit · stereo · 9,8 MB`, leaving out whatever
 * the server did not know. LMS sends `bitDepth` 0 for lossy formats, which is
 * "not applicable" rather than "zero bits", so it is dropped like an absent one.
 *
 * @param {Object} track
 * @param {{ mono: string, stereo: string, channels: function(number): string }} words
 *   The channel-count vocabulary, passed in because it is translated.
 * @returns {string}
 */
export function formatSummary(track, words) {
  if (!track) return "";
  const parts = [];
  if (track.suffix) parts.push(String(track.suffix).toUpperCase());
  if (track.bitRate > 0) parts.push(`${track.bitRate} kbps`);
  if (track.samplingRate > 0) {
    const kHz = track.samplingRate / 1000;
    parts.push(`${kHz.toLocaleString(undefined, { maximumFractionDigits: 1 })} kHz`);
  }
  if (track.bitDepth > 0) parts.push(`${track.bitDepth} bit`);
  if (track.channelCount === 1) parts.push(words.mono);
  else if (track.channelCount === 2) parts.push(words.stereo);
  else if (track.channelCount > 2) parts.push(words.channels(track.channelCount));
  if (track.size > 0) parts.push(formatBytes(track.size));
  return parts.join(" · ");
}

/** True when there is anything at all to put in the file section. */
export function hasFileDetails(track) {
  return !!(
    track &&
    (track.path || track.suffix || track.bitRate > 0 || track.size > 0 || track.created)
  );
}

/**
 * Tag names the sheet already renders as their own row or chip, so the raw
 * tag list below them does not repeat what is on screen. Lower-case, as the
 * tagger records them.
 */
const SHOWN_ELSEWHERE = new Set([
  "title",
  "artist",
  "album",
  "albumartist",
  "genre",
  "date",
  "originaldate",
  "year",
  "publisher",
  "label",
  "tracknumber",
  "discnumber",
  "festival",
  "mood",
  "rating",
  "parsed",
  "bpm",
  "catalognumber",
  "copyright",
  "original_artist",
  "original_title",
  "remixer",
  "podcast",
  "comment",
]);

/** One string per tag value list, or null when the tag is absent or empty. */
function joined(tags, name) {
  const value = tags?.[name];
  const list = Array.isArray(value) ? value : value == null ? [] : [value];
  const text = list
    .map((v) => String(v).trim())
    .filter(Boolean)
    .join(", ");
  return text || null;
}

/** The attribution GetSongBPM asks for when its tempo helped choose a track's octave. */
export const GETSONGBPM_CREDIT = Object.freeze({
  name: "GetSongBPM",
  href: "https://getsongbpm.com",
});

/**
 * The named rows the sheet shows under "Tags", from MuMa's answer to
 * `/api/library/tracks/by-path` plus the LMS song object. Each row is
 * `{ key, value, href?, view?, manual? }`, with `key` an i18n key under `track.` so
 * the component only has to translate and print. `view` is a router target
 * for rows that are a place to go: a channel curated as a label opens that
 * label, one curated as an artist opens a search for the name (the artist
 * id MuMa holds is not the one LMS navigates by).
 *
 * Order is what a listener asks about first: where it came from, then the
 * release facts, then the credits. Anything the tagger wrote that has no
 * named row is appended as raw `name: value` lines so nothing is hidden.
 *
 * @param {Object|null} details - MuMa's answer, or null when there was none.
 * @param {Object} track - The Subsonic song object.
 * @returns {Array<{key: string, value: string, href?: string, view?: string, raw?: boolean,
 *   manual?: boolean, credit?: {name: string, href: string}}>}
 */
export function tagRows(details, track) {
  const rows = [];
  const tags = details?.tags ?? {};

  for (const channel of details?.channels ?? []) {
    if (!channel?.name) continue;
    const row = { key: "channel", value: platformLabel(channel.platform, channel.name) };
    if (channel.label) row.view = `label:${channel.label}`;
    else if (channel.artist) row.view = `search:${channel.artist}`;
    rows.push(row);
  }
  if (details?.source_url) {
    rows.push({ key: "sourceUrl", value: details.source_url, href: details.source_url });
  }
  if (details?.source) rows.push({ key: "origin", value: titleCase(details.source) });

  // MuMa's effective BPM (a measurement, else the tag or old analyzer value folded into the
  // genre's band, marked "≈"), the file's own tag only when MuMa has none.
  const effective = formatBpm({ bpm: details?.bpm, approximate: details?.bpm_approximate });
  const tagged = joined(tags, "bpm");
  const bpm = effective || (tagged ? String(Math.round(Number(tagged)) || tagged) : "");
  if (bpm) {
    // A tempo set by hand says so, so nobody takes it for a measurement.
    const row =
      effective && details?.bpm_source === "manual"
        ? { key: "bpm", value: bpm, manual: true }
        : { key: "bpm", value: bpm };
    // GetSongBPM's terms ask for a link wherever its data helped (issue #152).
    if (
      effective &&
      details?.bpm_source === "measured" &&
      details?.bpm_external_source === "getsongbpm"
    ) {
      row.credit = GETSONGBPM_CREDIT;
    }
    rows.push(row);
  }
  const named = [
    ["catalogNumber", "catalognumber"],
    ["copyright", "copyright"],
    ["originalArtist", "original_artist"],
    ["originalTitle", "original_title"],
    ["remixer", "remixer"],
    ["podcast", "podcast"],
  ];
  for (const [key, name] of named) {
    const value = joined(tags, name);
    if (value) rows.push({ key, value });
  }
  const comment = joined(tags, "comment") || (track?.comment ? String(track.comment).trim() : null);
  if (comment) rows.push({ key: "comment", value: comment });
  if (details?.ml_genre) rows.push({ key: "mlGenre", value: details.ml_genre });

  for (const name of Object.keys(tags).sort()) {
    if (SHOWN_ELSEWHERE.has(name)) continue;
    const value = joined(tags, name);
    if (value) rows.push({ key: name, value, raw: true });
  }
  return rows;
}

function platformLabel(platform, name) {
  return platform ? `${name} (${titleCase(platform)})` : name;
}

function titleCase(word) {
  const text = String(word ?? "");
  return text ? text.charAt(0).toUpperCase() + text.slice(1).toLowerCase() : "";
}
