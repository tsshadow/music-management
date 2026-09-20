import { describe, it, expect, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { get } from "svelte/store";
import TrackRowCompact from "../../src/lib/TrackRowCompact.svelte";
import { currentTrack, playerState } from "../../src/lib/store.js";
import { missingArtistImages } from "../../src/lib/coverArt.js";

const TRACK = { id: "song-1", title: "Raise Your Fist", artist: "Angerfist", artistId: "artist-1" };

afterEach(() => {
  currentTrack.set(null);
  playerState.update((s) => ({ ...s, playing: false }));
  missingArtistImages.clear();
});

/**
 * A track with no cover and no portrait shows its title twice -- once as the row's real title,
 * once inside `Artwork`'s tinted fallback panel -- so the genuine title line is always the last
 * match.
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

  // The same chain the player uses: a track without a cover shows its first artist's portrait
  // before it resorts to the title panel. A shelf of title-only tiles was the thing being fixed.
  it("shows the first artist's portrait without a cover", () => {
    render(TrackRowCompact, { track: TRACK });

    expect(screen.queryByTestId("artwork-panel")).toBeNull();
    expect(screen.getByAltText("Raise Your Fist").getAttribute("src")).toContain(
      "/api/artists/Angerfist/image",
    );
  });

  it("falls back to the tinted panel once the portrait fails to load", async () => {
    render(TrackRowCompact, { track: TRACK });

    await fireEvent.error(screen.getByAltText("Raise Your Fist"));

    expect(screen.getByTestId("artwork-panel")).toBeTruthy();
  });

  // MuMa answers "no portrait" with a 404 the browser never caches, so a failed URL is
  // remembered: the next row of the same artist starts at the panel instead of asking again.
  it("starts at the panel for an artist whose portrait already failed this session", async () => {
    const first = render(TrackRowCompact, { track: TRACK });
    await fireEvent.error(screen.getByAltText("Raise Your Fist"));
    first.unmount();

    render(TrackRowCompact, { track: { ...TRACK, id: "song-2", title: "Encore" } });

    expect(screen.queryByAltText("Encore")).toBeNull();
    expect(screen.getByTestId("artwork-panel")).toBeTruthy();
  });

  it("falls back to the tinted panel without a cover or an artist", () => {
    render(TrackRowCompact, { track: { ...TRACK, artist: "", artistId: null } });

    expect(screen.getByTestId("artwork-panel")).toBeTruthy();
  });
});
