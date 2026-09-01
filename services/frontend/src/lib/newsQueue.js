/**
 * What to put back after a news bulletin.
 *
 * A track returns to its position; a radio channel does not, because the server
 * owns that timeline and a stored position would be wrong by exactly the length
 * of the bulletin. Pure, so it can be tested without a DOM — the mirror of
 * NewsQueueRules.kt on mobile, the way radioSync.js mirrors RadioSync.kt.
 */

/** Snapshot the player, or null when there was nothing playing to come back to. */
export function snapshotOf({ trackId, positionSeconds, radioChannel }) {
  if (!trackId && !radioChannel) return null;
  return {
    trackId: trackId ?? null,
    positionSeconds: positionSeconds ?? 0,
    radioChannel: radioChannel ?? null,
  };
}

/** Decide how to resume once the bulletin has finished. */
export function restoreTarget(snapshot) {
  if (!snapshot) return { action: "none" };
  if (snapshot.radioChannel) return { action: "retune", channel: snapshot.radioChannel };
  if (!snapshot.trackId) return { action: "none" };
  return {
    action: "track",
    trackId: snapshot.trackId,
    positionSeconds: snapshot.positionSeconds,
  };
}

/** Where a bulletin's audio lives. The API key travels as a header, not here. */
export function bulletinStreamUrl(apiBase, id) {
  return `${apiBase}/api/news/bulletins/${id}/stream`;
}
