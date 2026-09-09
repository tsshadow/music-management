import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/svelte";
import TrackList from "../../src/lib/TrackList.svelte";

const track = (extra = {}) => ({
  id: "1",
  title: "Track",
  artist: "Artist",
  album: "Album",
  albumId: "a1",
  duration: 200,
  ...extra,
});

describe("TrackList genre column", () => {
  it("links every genre of a multi-genre track separately", async () => {
    const onnavigate = vi.fn();
    render(TrackList, { tracks: [track({ genre: "hardstyle,hardcore" })], onnavigate });

    const hardstyle = screen.getByText("hardstyle");
    const hardcore = screen.getByText("hardcore");

    await hardstyle.click();
    expect(onnavigate).toHaveBeenCalledWith("genre:hardstyle");

    await hardcore.click();
    expect(onnavigate).toHaveBeenCalledWith("genre:hardcore");
  });

  it("keeps the genres readable as one comma-separated string", () => {
    render(TrackList, { tracks: [track({ genre: "hardstyle, hardcore" })], onnavigate: vi.fn() });

    const cell = screen.getByTitle("hardstyle, hardcore");
    expect(cell.textContent.replace(/\s+/g, " ").trim()).toBe("hardstyle, hardcore");
  });

  it("still links a single genre", async () => {
    const onnavigate = vi.fn();
    render(TrackList, { tracks: [track({ genre: "techno" })], onnavigate });

    await screen.getByText("techno").click();
    expect(onnavigate).toHaveBeenCalledWith("genre:techno");
  });
});

describe("TrackList versions", () => {
  const subsonicTracks = (tracks) =>
    vi.fn(async () => ({
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok", tracks: { track: tracks } } }),
    }));

  it("offers the versions of a song the server has grouped", () => {
    render(TrackList, { tracks: [track({ workId: 42 })], onnavigate: vi.fn() });
    expect(screen.getByTitle("Versies")).toBeTruthy();
  });

  it("offers nothing for a track the server has not grouped", () => {
    // Half the library carries no work while the worker catches up, and a button that
    // opens an empty list is worse than no button.
    render(TrackList, { tracks: [track()], onnavigate: vi.fn() });
    expect(screen.queryByTitle("Versies")).toBeNull();
  });

  it("asks the server for the versions rather than reading the page", async () => {
    // The row on screen is the one version that survived collapsing; the others never
    // reached the browser.
    globalThis.fetch = subsonicTracks([
      { id: "1", title: "Track", isCanonical: true, suffix: "flac" },
      { id: "2", title: "Track (Extended Mix)", isCanonical: false, suffix: "mp3", bitRate: 320 },
    ]);
    render(TrackList, { tracks: [track({ workId: 42 })], onnavigate: vi.fn() });

    await screen.getByTitle("Versies").click();

    await vi.waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(globalThis.fetch.mock.calls[0][0]).toContain("workId=42");
    await vi.waitFor(() => expect(screen.getByText("Track (Extended Mix)")).toBeTruthy());
    expect(screen.getByText("beste versie")).toBeTruthy();
  });

  it("says so when a song has only the one version", async () => {
    globalThis.fetch = subsonicTracks([{ id: "1", title: "Track", isCanonical: true }]);
    render(TrackList, { tracks: [track({ workId: 42 })], onnavigate: vi.fn() });

    await screen.getByTitle("Versies").click();

    await vi.waitFor(() =>
      expect(screen.getByText("Dit is de enige versie van dit nummer.")).toBeTruthy(),
    );
  });
});
