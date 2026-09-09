/**
 * One row per song, using the answer the server already has.
 *
 * This used to guess: it normalised the artist and the title into a key, scored each
 * candidate on format and bitrate and version words, and summed those scores. Summing is
 * what made it wrong -- a 320kbps SoundCloud rip (+5200) beat an official 192kbps radio
 * edit (+2500), the exact inversion the version model was built to remove.
 *
 * muma decides it now, with the label provenance and the download archives that neither
 * this browser nor LMS can see, and the answer travels on every track as `workId` and
 * `isCanonical` (migration 118). What is left here is applying it.
 *
 * The server collapses the same way when `deduplicate=true` is sent, so on those lists
 * this is a second pass over an already-collapsed list and finds nothing to do. It still
 * runs, because search results and curated playlists collapse here and nowhere else.
 */

/**
 * The song a track belongs to.
 *
 * A track muma has not grouped yet -- at the moment roughly half the library, while the
 * worker works through its backlog -- gets a key of its own, so it is shown rather than
 * folded into somebody else's song. Hiding what is not yet understood is the one failure
 * this must not have.
 *
 * @param {Object} track - A Subsonic track.
 * @returns {string} The grouping key.
 */
export function getDeduplicateKey(track) {
  const workId = track.workId;
  if (workId !== undefined && workId !== null && workId !== "" && Number(workId) > 0) {
    return `work:${workId}`;
  }
  return `track:${track.id}`;
}

/**
 * Whether the server named this track the version to play.
 *
 * Absent means yes: an older server, or a response that predates migration 118, must not
 * turn every track into a non-canonical one and empty the list.
 *
 * @param {Object} track - A Subsonic track.
 * @returns {boolean}
 */
export function isCanonical(track) {
  const value = track.isCanonical;
  if (value === undefined || value === null || value === "") return true;
  return value === true || value === "true" || value === 1 || value === "1";
}

/**
 * Ranks two versions of one song when neither is the canonical.
 *
 * That happens while a work is being regrouped: its members are known, its winner is not
 * recomputed yet. `versionScore` is the server's own ordering -- provenance, then version
 * kind, then format -- so this reads it rather than inventing a second one.
 *
 * @param {Object} track - A Subsonic track.
 * @returns {number}
 */
export function getTrackScore(track) {
  const score = Number(track.versionScore);
  return Number.isFinite(score) ? score : 0;
}

/**
 * Keeps one track per song: the canonical, or the best-scoring version when the server
 * has not named one yet.
 *
 * @param {Object[]} tracks - Array of track objects.
 * @param {Map<string, Object>} [seenBefore] - Songs already shown in an earlier batch.
 * @returns {Object[]} One track per song, in the order the server returned them.
 */
export function deduplicateTracks(tracks, seenBefore = new Map()) {
  const currentBatchBest = new Map();

  for (const track of tracks) {
    const key = getDeduplicateKey(track);

    // Already shown in a previous batch: infinite scroll must not repeat a song.
    if (seenBefore.has(key)) {
      continue;
    }

    const existing = currentBatchBest.get(key);
    if (!existing) {
      currentBatchBest.set(key, track);
      continue;
    }

    // The server named a winner; nothing here re-decides that.
    if (isCanonical(track) && !isCanonical(existing)) {
      currentBatchBest.set(key, track);
    } else if (!isCanonical(existing) && getTrackScore(track) > getTrackScore(existing)) {
      currentBatchBest.set(key, track);
    }
  }

  return Array.from(currentBatchBest.values());
}

/**
 * Every version of a song, best first, from a list that still holds all of them.
 *
 * Used by the version list behind a row. The order is the server's: canonical first, then
 * by score.
 *
 * @param {Object[]} tracks - Array of track objects.
 * @param {string} key - The grouping key, from getDeduplicateKey.
 * @returns {Object[]} The versions of that one song.
 */
export function versionsOf(tracks, key) {
  return tracks
    .filter((track) => getDeduplicateKey(track) === key)
    .sort((a, b) => {
      if (isCanonical(a) !== isCanonical(b)) return isCanonical(a) ? -1 : 1;
      return getTrackScore(b) - getTrackScore(a);
    });
}
