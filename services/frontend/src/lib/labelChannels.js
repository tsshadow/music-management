/**
 * The channels linked to a label or an artist, for the "Kanalen" section on the label page
 * (issue #122), the artist page and the label edit page (issue #126).
 *
 * A channel is the SoundCloud, YouTube or Telegram account a file came in through; a curator
 * links it to its label or artist under Management > Downloaders > Links
 * (docs/designs/channel-links). The answer is cached per kind and name for the session, so going
 * back to a page shows its channels at once and refreshes them behind the scenes (styleguide,
 * Loading States: Refresh).
 */
import { apiBase, fetchMumaJson, getHeaders } from "./mumaApi.js";
import { listOf, subsonicJson } from "./subsonic.js";

/** Platform names as the page shows them. */
export const PLATFORM_LABELS = {
  soundcloud: "SoundCloud",
  youtube: "YouTube",
  telegram: "Telegram",
};

/** What a channel can be linked to; each has its own list endpoint, `/by-<kind>`. */
export const CHANNEL_KINDS = ["label", "artist"];

/** @type {Map<string, Array<Object>>} Last answer per kind and name. */
const cache = new Map();

function cacheKey(kind, name) {
  return `${kind}\n${name}`;
}

/**
 * The last known channels of a label or artist, or undefined when this session never asked.
 * @param {'label'|'artist'} kind
 * @param {string} name
 * @returns {Array<Object>|undefined}
 */
export function cachedLinkedChannels(kind, name) {
  return cache.get(cacheKey(kind, name));
}

/** Forget every cached answer (tests, sign-out). */
export function clearLinkedChannels() {
  cache.clear();
}

/**
 * Fetch the channels linked to a label or artist, busiest first, and remember the answer.
 *
 * Each row also names the channel's other link: `artist` on a label's channel, `label` on an
 * artist's.
 *
 * @param {'label'|'artist'} kind
 * @param {string} name - The label's or artist's name. The artist page's route carries the LMS
 *   id, which means nothing to MuMa, so the name is the key for both.
 * @returns {Promise<Array<{id: number, platform: string, name: string, track_count: number,
 *   album: string|null, source_url: string|null}>>}
 */
export async function fetchLinkedChannels(kind, name) {
  if (!CHANNEL_KINDS.includes(kind)) throw new Error(`Unknown channel kind: ${kind}`);
  const url = `${apiBase()}/api/channel-links/by-${kind}?name=${encodeURIComponent(name)}`;
  const rows = await fetchMumaJson(url, { headers: getHeaders() });
  const channels = Array.isArray(rows) ? rows : [];
  cache.set(cacheKey(kind, name), channels);
  return channels;
}

/**
 * Remove a channel's link of this kind (`DELETE /api/channel-links/channels/{id}/{kind}`), and
 * drop the channel from the cached answer for `name`. The backend rejects the proposal behind the
 * link and queues the channel's files for the tagger.
 *
 * @param {'label'|'artist'} kind
 * @param {string} name - The label or artist the channel is unlinked from.
 * @param {{id: number}} channel
 * @returns {Promise<{status: string, queued: number}>}
 */
export async function unlinkChannel(kind, name, channel) {
  if (!CHANNEL_KINDS.includes(kind)) throw new Error(`Unknown channel kind: ${kind}`);
  const url = `${apiBase()}/api/channel-links/channels/${channel.id}/${kind}`;
  const result = await fetchMumaJson(url, { method: "DELETE", headers: getHeaders() });
  const cached = cache.get(cacheKey(kind, name));
  if (cached)
    cache.set(
      cacheKey(kind, name),
      cached.filter((row) => row.id !== channel.id),
    );
  return result;
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
