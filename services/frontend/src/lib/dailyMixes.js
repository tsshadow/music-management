/**
 * The five daily mixes, turned into cards: a colour, an optional cover, and the title/subtitle
 * MuMa already computed. Worked out once here so the desktop shelf, the phone's overview shelf
 * and the phone's own "Daily mixes" page draw the same five cards.
 */
import { DAILY_MIXES, DAILY_MIX_ARTIST, DAILY_MIX_BANDS, fetchFeed, listFeeds } from "./feeds.js";
import { apiBase } from "./mumaApi.js";
import { gatedFetch } from "./mumaGate.js";
import { tintFor } from "./genreTints.js";

/** soft green, mid brand blue, hard red -- the fixed ramp for when no genre tint answers. */
const BAND_RAMP = ["#1DB954", "#2D5AFC", "#E23744"];

/** A small, fixed palette for a name with no image of its own -- an artist or a label. */
const HASH_PALETTE = [
  "#E13300",
  "#7358FF",
  "#0D73EC",
  "#148A08",
  "#8C1932",
  "#503750",
  "#B06E00",
  "#1E3264",
];

/**
 * A small, stable colour for a name, so the same artist or label draws the same tile every day.
 *
 * @param {string} name
 * @returns {string} A hex colour from the fixed palette.
 */
export function hashColor(name) {
  const value = String(name ?? "");
  let hash = 0;
  for (let i = 0; i < value.length; i++) hash = (hash * 31 + value.charCodeAt(i)) | 0;
  return HASH_PALETTE[Math.abs(hash) % HASH_PALETTE.length];
}

/**
 * Whether an image actually loads, rather than 404ing -- an artist may have no photo at all.
 *
 * Asked with `fetch` rather than an `Image`: the artist-image endpoint sits behind the same
 * LMS proxy gate as every other MuMa call, and a refusal there is a 503 an `Image` can only
 * report as "failed to load". Going through `gatedFetch` takes a slot like the rest, retries
 * a refusal, and holds nothing open when the answer never comes. The browser keeps the body
 * in its HTTP cache, so the `<img>` drawn afterwards from the same URL does not fetch twice.
 *
 * @param {string} url
 * @returns {Promise<boolean>}
 */
export async function imageLoads(url) {
  try {
    const response = await gatedFetch(url);
    return Boolean(response?.ok);
  } catch {
    return false;
  }
}

function genreNames(track) {
  return Array.isArray(track?.genres) ? track.genres.filter(Boolean) : [];
}

/** The genre named most often across a mix's own tracks, or null when none carry one. */
function topGenre(tracks) {
  const counts = new Map();
  for (const track of tracks ?? []) {
    for (const genre of genreNames(track)) counts.set(genre, (counts.get(genre) ?? 0) + 1);
  }
  let best = null;
  let bestCount = 0;
  for (const [genre, count] of counts) {
    if (count > bestCount) {
      best = genre;
      bestCount = count;
    }
  }
  return best;
}

/**
 * The one card for a spectrum band: the genre tint of its own most common genre when one is
 * playing there, else the fixed soft/mid/hard ramp by the band's position.
 *
 * @param {string} slug
 * @param {Object} info - `{title, subtitle}` from `listFeeds()`, or a fallback when absent.
 * @param {Object<string,string>} tints
 * @returns {Promise<Object>}
 */
async function bandCard(slug, info, tints) {
  const detail = await fetchFeed(slug, 10);
  const genre = topGenre(detail.tracks);
  const position = DAILY_MIX_BANDS.indexOf(slug);
  const color = tintFor(tints, genre) ?? BAND_RAMP[position === -1 ? 0 : position];
  return { slug, title: info.title, subtitle: info.subtitle, color, cover: null };
}

/**
 * The card for a rotating mix (the day's artist or label): its own image when the name has one
 * (artist only -- there is no label-image endpoint), else a colour from its name.
 *
 * @param {string} slug
 * @param {Object} info
 * @param {string} authParams
 * @returns {Promise<Object>}
 */
async function rotatingCard(slug, info, authParams) {
  const color = hashColor(info.title);
  if (slug !== DAILY_MIX_ARTIST || !info.title || !authParams) {
    return { slug, title: info.title, subtitle: info.subtitle, color, cover: null };
  }
  const url = `${apiBase()}/api/artists/${encodeURIComponent(info.title)}/image?${authParams}`;
  const cover = (await imageLoads(url)) ? url : null;
  return { slug, title: info.title, subtitle: info.subtitle, color, cover };
}

/**
 * Builds the five daily-mix cards, in display order: soft, mid, hard, the day's artist, the
 * day's label.
 *
 * @param {Object<string,string>} tints - genre name (lowercased) -> colour, already fetched.
 * @param {string} authParams - Subsonic credentials, for the artist-image check.
 * @returns {Promise<Object[]>} `{slug, title, subtitle, color, cover}`, one per mix.
 */
export async function loadDailyMixCards(tints, authParams) {
  const feeds = await listFeeds();
  const bySlug = new Map(feeds.map((feed) => [feed.slug, feed]));

  return Promise.all(
    DAILY_MIXES.map((slug) => {
      const info = bySlug.get(slug) ?? { slug, title: slug, subtitle: null };
      return DAILY_MIX_BANDS.includes(slug)
        ? bandCard(slug, info, tints)
        : rotatingCard(slug, info, authParams);
    }),
  );
}
