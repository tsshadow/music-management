import { describe, it, expect, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { get } from "svelte/store";
import TrackRowCompact from "../../src/lib/TrackRowCompact.svelte";
import { currentTrack, playerState } from "../../src/lib/store.js";

const TRACK = { id: "song-1", title: "Raise Your Fist", artist: "Angerfist", artistId: "artist-1" };

afterEach(() => {
  currentTrack.set(null);
  playerState.update((s) => ({ ...s, playing: false }));
});

/**
 * A track with no cover shows its title twice -- once as the row's real title, once inside
 * `Artwork`'s tinted fallback panel (see `TrackCard.svelte`'s tests for the same shape) --
 * so the genuine title line is always the last match.
 */
function titleText(text) {
  return screen.getAllByText(text).pop();
}

describe("TrackRowCompact", () => {
  it("shows the title and artist", () => {
    render(TrackRowCompact, { track: TRACK });

    expect(titleText("Raise Your Fist")).toBeTruthy();
    expect(screen.getByText("Angerfist")).toBeTruthy();
  });

  // The whole row plays the track, the same one-tap behaviour `TrackCard.svelte` has always
  // had -- both now go through the shared `playTrack()` helper instead of two copies of it.
  it("plays the track when tapped", async () => {
    render(TrackRowCompact, { track: TRACK });

    await fireEvent.click(screen.getByTestId("track-row-compact"));

    expect(get(currentTrack)).toEqual(TRACK);
    expect(get(playerState).playing).toBe(true);
  });

  it("plays the track on Enter, for keyboard use", async () => {
    render(TrackRowCompact, { track: TRACK });

    await fireEvent.keyDown(screen.getByTestId("track-row-compact"), { key: "Enter" });

    expect(get(currentTrack)).toEqual(TRACK);
  });

  it("falls back to the tinted panel without a cover", () => {
    render(TrackRowCompact, { track: TRACK });

    expect(screen.getByTestId("artwork-panel")).toBeTruthy();
  });
});
