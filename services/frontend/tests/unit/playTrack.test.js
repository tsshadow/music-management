import { describe, it, expect, afterEach } from "vitest";
import { get } from "svelte/store";
import { playTrack } from "../../src/lib/playTrack.js";
import { currentTrack, playerState } from "../../src/lib/store.js";

const TRACK = { id: "song-1", title: "Raise Your Fist", artist: "Angerfist" };

afterEach(() => {
  currentTrack.set(null);
  playerState.update((s) => ({ ...s, playing: false }));
});

/**
 * `TrackCard.svelte` and `TrackRowCompact.svelte` both used to keep their own copy of these
 * two lines; this is the one place that does it now.
 */
describe("playTrack", () => {
  it("sets the track as current and starts playback", () => {
    playTrack(TRACK);

    expect(get(currentTrack)).toEqual(TRACK);
    expect(get(playerState).playing).toBe(true);
  });

  it("keeps the rest of the player state untouched", () => {
    playerState.update((s) => ({ ...s, playing: false, volume: 0.5 }));

    playTrack(TRACK);

    expect(get(playerState)).toMatchObject({ playing: true, volume: 0.5 });
  });
});
