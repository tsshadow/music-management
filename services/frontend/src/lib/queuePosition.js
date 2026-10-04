/**
 * The text for a queue row's place in the play order, "3/500".
 *
 * @param {number} index - Zero-based index of the row in the queue as it is played now.
 * @param {number} length - Number of tracks in the queue.
 * @returns {string} One-based position over the length.
 */
export function queuePosition(index, length) {
  return `${index + 1}/${length}`;
}

/**
 * The widest the position text gets for a queue of this length, in characters ("500/500" is 7).
 * Used as a minimum width so every row's position column is equally wide.
 *
 * @param {number} length - Number of tracks in the queue.
 * @returns {number} Character count of the last row's position text.
 */
export function queuePositionWidth(length) {
  return queuePosition(length - 1, length).length;
}
