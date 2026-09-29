/**
 * The Home cards for the personalised feeds: the release radar and the five daily mixes, each a
 * colour, an optional cover, and the title/subtitle MuMa already computed. Worked out once here
 * so the desktop shelf, the phone's overview shelf and the phone's own "Daily mixes" page draw
 * the same cards.
 *
 * Built from `GET /api/feeds` alone. Home never asks for a feed's tracks: a card is a door, and
 * what is behind it is fetched when it is opened (`FeedView`). The three band cards used to fetch
 * ten tracks each to pick a genre tint, which was three full feed builds per Home load for three
 * hex values -- docs/designs/feeds/home-load.md. The ramp is the colour now.
 */
import {
  DAILY_MIX_ARTIST,
  DAILY_MIX_BANDS,
  RELEASE_RADAR,
  SHELF_FEEDS,
  listFeeds,
} from "./feeds.js";
import { apiBase } from "./mumaApi.js";
import { gatedFetch } from "./mumaGate.js";

/** The radar's own blue -- the same one the phone's quick-access tile has always used. */
export const RADAR_COLOR = "#0D73EC";

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

/**
 * The cards, in display order: the radar first when asked for, then soft, mid, hard, the day's
 * artist, the day's label and "Oude hitjes". Publish `cards` at once; then call `refine(onRefine)`, which hands
 * back a replacement card (keyed by slug) for the one decoration that arrives later.
 *
 * @param {string} authParams - Subsonic credentials, for the artist-image probe.
 * @param {{radar?: boolean}} [options] - Whether the release radar leads the row.
 * @returns {Promise<{cards: Object[], refine: (onRefine: (card: Object) => void) => Promise<void>}>}
 */
export async function loadDailyMixCards(authParams, { radar = false } = {}) {
  const feeds = await listFeeds();
  const bySlug = new Map(feeds.map((feed) => [feed.slug, feed]));
  const slugs = radar ? [RELEASE_RADAR, ...SHELF_FEEDS] : SHELF_FEEDS;
  const cards = slugs.map((slug) => {
    const info = bySlug.get(slug) ?? { title: slug, subtitle: null };
    const position = DAILY_MIX_BANDS.indexOf(slug);
    let color = hashColor(info.title);
    if (slug === RELEASE_RADAR) color = RADAR_COLOR;
    else if (position >= 0) color = BAND_RAMP[position];
    return { slug, title: info.title, subtitle: info.subtitle, color, cover: null };
  });

  /**
   * The one lookup a card still makes after it is on screen: the day's artist may have a photo.
   * Never a feed, never tracks. A failed probe leaves the card as it was.
   */
  async function refine(onRefine) {
    const artist = cards.find((card) => card.slug === DAILY_MIX_ARTIST);
    if (!artist || !artist.title || !authParams) return;
    try {
      const cover = `${apiBase()}/api/artists/${encodeURIComponent(artist.title)}/image?${authParams}`;
      if (await imageLoads(cover)) onRefine({ ...artist, cover });
    } catch {
      // Optional decoration must never hide an otherwise playable card.
    }
  }
  return { cards, refine };
}
