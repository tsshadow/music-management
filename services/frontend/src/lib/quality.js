/**
 * The values of LMS's `QUALITY` cluster, best first.
 *
 * The scanner files every track under exactly one of these from its codec and bitrate -- the same
 * five tiers muma ranks versions of a song by. A filter asks for a floor, never for one tier
 * alone below the top: "320" means 320 and lossless. `getSpotifyTracks` takes the floor as
 * `minQuality` and expands it itself; `getSongs` takes clusters, so {@link qualityAtLeast} expands
 * it here for the preset path.
 */

export const QUALITY_TIERS = Object.freeze(["lossless", "320", "aac", "192", "low"]);

/**
 * The floors worth offering: a floor at the bottom tier is every track, which "no filter" already
 * says, and two entries reading "Everything" in one list is a question nobody should have to ask.
 */
export const QUALITY_FLOORS = Object.freeze(QUALITY_TIERS.slice(0, -1));

/** i18n keys naming each tier as a floor: "Lossless", "320 kbps of beter", ... */
export const QUALITY_LABEL_KEYS = Object.freeze({
  lossless: "filter.quality.lossless",
  320: "filter.quality.kbps320",
  aac: "filter.quality.aac",
  192: "filter.quality.kbps192",
  low: "filter.quality.low",
});

/**
 * Every tier from the top down to `floor`, or null for a floor that is not a tier -- a preset
 * written by a newer app, or nothing at all -- so the caller sends no cluster rather than one the
 * server would refuse the whole request over.
 *
 * @param {string|null|undefined} floor
 * @returns {string[]|null}
 */
export function qualityAtLeast(floor) {
  const index = QUALITY_TIERS.indexOf(
    String(floor ?? "")
      .trim()
      .toLowerCase(),
  );
  if (index < 0) return null;
  return QUALITY_TIERS.slice(0, index + 1);
}
