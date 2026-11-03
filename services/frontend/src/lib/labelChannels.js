/**
 * The channels linked to a label, for the label page's "Kanalen" section (issue #122).
 *
 * A channel is the SoundCloud, YouTube or Telegram account a file came in through; a curator
 * links it to its label under Management > Downloaders > Links (docs/designs/channel-links).
 * The answer is cached per label for the session, so going back to a label page shows its
 * channels at once and refreshes them behind the scenes (styleguide, Loading States: Refresh).
 */
import { apiBase, fetchMumaJson, getHeaders } from "./mumaApi.js";
import { listOf, subsonicJson } from "./subsonic.js";

/** Platform names as the page shows them. */
export const PLATFORM_LABELS = {
  soundcloud: "SoundCloud",
  youtube: "YouTube",
  telegram: "Telegram",
};

/** @type {Map<string, Array<Object>>} Last answer per label name. */
const cache = new Map();

/**
 * The label's last known channels, or undefined when this session never asked.
 * @param {string} label
 * @returns {Array<Object>|undefined}
 */
export function cachedLabelChannels(label) {
  return cache.get(label);
}

/** Forget every cached answer (tests, sign-out). */
export function clearLabelChannels() {
  cache.clear();
}

/**
 * Fetch the channels linked to a label, busiest first, and remember the answer.
 * @param {string} label - The label's name, as the label page's route carries it.
 * @returns {Promise<Array<{id: number, platform: string, name: string, track_count: number,
 *   artist: {id: number, name: string}|null, album: string|null, source_url: string|null}>>}
 */
export async function fetchLabelChannels(label) {
  const url = `${apiBase()}/api/channel-links/by-label?name=${encodeURIComponent(label)}`;
  const rows = await fetchMumaJson(url, { headers: getHeaders() });
  const channels = Array.isArray(rows) ? rows : [];
  cache.set(label, channels);
  return channels;
}

/**
 * The library album a channel's tracks sit under, as an `album:<id>` view, or null.
 *
 * The tagger files every download of a channel under the album `<Platform> (<channel>)`, so
 * that album is the channel's track list. Only an exact (case-insensitive) name match counts:
 * a near miss would open some other channel's tracks.
 *
 * @param {{album: string|null}} channel
 * @returns {Promise<string|null>}
 */
export async function channelAlbumView(channel) {
  if (!channel?.album) return null;
  try {
    const data = await subsonicJson("search3", {
      query: channel.album,
      artistCount: 0,
      albumCount: 5,
      songCount: 0,
    });
    const wanted = channel.album.toLowerCase();
    const match = listOf(data, "searchResult3.album").find(
      (album) => album.name?.toLowerCase() === wanted,
    );
    return match?.id ? `album:${match.id}` : null;
  } catch {
    return null;
  }
}

/**
 * Where tapping a channel goes: its track list in the library when one is found, else the
 * account's page on the platform, else a library search for the channel's name.
 *
 * @param {Object} channel
 * @returns {Promise<{view: string}|{url: string}>}
 */
export async function channelDestination(channel) {
  const view = await channelAlbumView(channel);
  if (view) return { view };
  if (channel?.source_url) return { url: channel.source_url };
  return { view: `search:${channel?.name ?? ""}` };
}
