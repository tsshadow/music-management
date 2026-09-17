import { currentTrack, playerState } from "./store.js";

/**
 * Starts playback of a track from a card or row that only ever plays the one
 * track it shows -- `TrackCard.svelte` and `TrackRowCompact.svelte` used to
 * each keep their own two-line copy of this (`currentTrack.set` then flip
 * `playerState.playing`), which is exactly the kind of duplicate that drifts
 * the moment one of them grows a third line and the other does not.
 *
 * @param {object} track
 */
export function playTrack(track) {
  currentTrack.set(track);
  playerState.update((s) => ({ ...s, playing: true }));
}
