/**
 * What the full-screen player's header and background show, shared by `NowPlaying.svelte` and
 * its seeded stand-in `NowPlayingShell.svelte` (issue #119), so the swap from one to the other
 * changes nothing on screen.
 */
import { placeTitle } from "./recentPlaces.js";
import { viewLabel } from "./queue.js";

/**
 * The "Playing from" line: the place the current queue was started from (a genre, a playlist,
 * an artist ...) when `startQueue` recorded one -- see `store.js`'s `queueSource` and
 * `docs/designs/phone-ui-polish/technical.md`, section E -- else the track's own album, else
 * the generic caption.
 *
 * @param {{name?: string, view?: string}|null|undefined} source - `$queueSource`.
 * @param {{album?: string}|null|undefined} track
 * @param {string} fallback - The translated "Queue" caption.
 * @returns {string}
 */
export function playingFromLabel(source, track, fallback) {
  return (
    source?.name ??
    placeTitle({ view: source?.view }) ??
    viewLabel(source?.view) ??
    track?.album ??
    fallback
  );
}

/**
 * The screen is never flat black: a vertical gradient fades from 55% of the playing track's
 * genre tint at the top into the standard dark background by 60% of the way down, so the tint
 * reads as "this screen" rather than a bar of colour behind the artwork. No tint (no genre, or
 * none the server has a colour for) is the plain neutral surface.
 *
 * @param {string|null|undefined} tint
 * @returns {string} An inline `style` value.
 */
export function nowPlayingBackground(tint) {
  return tint
    ? `background: linear-gradient(to bottom, color-mix(in srgb, ${tint} 55%, #121212) 0%, #121212 60%)`
    : "background-color: #121212";
}
