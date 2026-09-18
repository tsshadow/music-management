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
 * Asked with `fetch` rather than an `Image`: the artist-image endpoint sits behind the LMS proxy
 * gate alongside the other LMS-owned routes, and a refusal there is a 503 an `Image` can only
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
 * Builds cards from the listing alone. Call `refine(onRefine)` after publishing them;
 * each successful refinement emits a replacement card independently, keyed by slug.
 * Failures and missing tints/images leave the original card untouched.
 *
 * @param {Object<string,string>} tints
 * @param {string} authParams
 * @returns {Promise<{cards: Object[], refine: (onRefine: (card: Object) => void) => Promise<void>}>}
 */
export async function loadDailyMixCards(tints, authParams) {
  const feeds = await listFeeds();
  const bySlug = new Map(feeds.map((feed) => [feed.slug, feed]));
  const cards = DAILY_MIXES.map((slug) => {
    const info = bySlug.get(slug) ?? { title: slug, subtitle: null };
    const position = DAILY_MIX_BANDS.indexOf(slug);
    return {
      slug,
      title: info.title,
      subtitle: info.subtitle,
      color: position >= 0 ? BAND_RAMP[position] : hashColor(info.title),
      cover: null,
    };
  });

  /** Runs optional colour and image lookups without delaying the initial cards. */
  async function refine(onRefine) {
    await Promise.all(
      cards.map(async (card) => {
        try {
          if (DAILY_MIX_BANDS.includes(card.slug)) {
            const detail = await fetchFeed(card.slug, 10);
            const color = tintFor(tints, topGenre(detail?.tracks));
            if (color != null) onRefine({ ...card, color });
          } else if (card.slug === DAILY_MIX_ARTIST && card.title && authParams) {
            const cover = `${apiBase()}/api/artists/${encodeURIComponent(card.title)}/image?${authParams}`;
            if (await imageLoads(cover)) onRefine({ ...card, cover });
          }
        } catch {
          // Optional decoration must never hide an otherwise playable card.
        }
      }),
    );
  }
  return { cards, refine };
}
