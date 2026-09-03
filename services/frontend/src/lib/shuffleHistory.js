/**
 * The trail of tracks shuffle play has already visited.
 *
 * Shuffling used to draw a fresh random track for both directions, so "previous"
 * never led back to where you came from: going A -> F and pressing previous
 * dropped you on some unrelated K. The trail fixes that by remembering the order
 * the tracks were actually played in, with a cursor that moves back and forth
 * through it. Only a step past the end of the trail draws a new random track.
 *
 * The functions are pure and hand back a new trail, so the player can keep it in
 * one piece of state and this file can be tested without an audio element.
 *
 * @typedef {Object} Trail
 * @property {string[]} ids - Track ids in the order they were played.
 * @property {number} position - Index in `ids` of the track playing now, -1 when empty.
 */

/** @returns {Trail} An empty trail. */
export function emptyTrail() {
  return { ids: [], position: -1 };
}

/**
 * Starts the trail at the track that is playing, discarding anything older.
 *
 * Called when the queue itself changes: the old trail names tracks that may no
 * longer be in it, and stepping back into them would play something the listener
 * cannot see.
 *
 * @param {string|null|undefined} id - Id of the track playing now.
 * @returns {Trail} The new trail.
 */
export function startTrail(id) {
  return id == null ? emptyTrail() : { ids: [String(id)], position: 0 };
}

/**
 * The id the trail is currently on.
 *
 * @param {Trail} trail
 * @returns {string|null}
 */
export function currentId(trail) {
  return trail.ids[trail.position] ?? null;
}

/**
 * Picks the next track, walking forward through the trail before drawing anew.
 *
 * Walking forward first is what makes previous-then-next symmetric: after
 * stepping back from F to A, next returns to F rather than to a third track.
 *
 * @param {Trail} trail - The trail so far.
 * @param {string[]} candidates - Ids of every track in the queue.
 * @param {() => number} random - Source of randomness, injectable for tests.
 * @returns {{trail: Trail, id: string|null}} The advanced trail and what to play.
 */
export function stepForward(trail, candidates, random = Math.random) {
  if (candidates.length === 0) return { trail, id: null };

  if (trail.position < trail.ids.length - 1) {
    const position = trail.position + 1;
    return { trail: { ...trail, position }, id: trail.ids[position] };
  }

  const id = drawId(candidates, currentId(trail), random);
  const ids = [...trail.ids, id];
  return { trail: { ids, position: ids.length - 1 }, id };
}

/**
 * Steps back to the track played before this one.
 *
 * At the start of the trail there is nothing to go back to, so the track that is
 * playing stays: restarting it is what every player does at the top of a queue,
 * and it beats jumping somewhere the listener has not been.
 *
 * @param {Trail} trail - The trail so far.
 * @returns {{trail: Trail, id: string|null}} The rewound trail and what to play.
 */
export function stepBack(trail) {
  if (trail.position <= 0) return { trail, id: currentId(trail) };

  const position = trail.position - 1;
  return { trail: { ...trail, position }, id: trail.ids[position] };
}

/**
 * Draws a random id, avoiding the one already playing.
 *
 * @param {string[]} candidates - Ids to choose from.
 * @param {string|null} avoid - The id playing now.
 * @param {() => number} random - Source of randomness.
 * @returns {string} The drawn id.
 */
function drawId(candidates, avoid, random) {
  const others = candidates.filter((id) => id !== avoid);
  const pool = others.length > 0 ? others : candidates;
  return pool[Math.floor(random() * pool.length)] ?? pool[0];
}
