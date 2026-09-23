import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import StarredView from "../../src/lib/StarredView.svelte";
import { credentials, currentTrack, playerState, playlist } from "../../src/lib/store.js";

const SONG = { id: "song-1", title: "Raise Your Fist", artist: "Angerfist", suffix: "flac" };
const ALBUM = { id: "album-1", name: "Close Combat", artist: "Angerfist" };
const ARTIST = { id: "artist-1", name: "Angerfist" };

function starred({ song = [SONG], album = [ALBUM], artist = [ARTIST] } = {}) {
  return vi.fn(async () => ({
    ok: true,
    json: async () => ({
      "subsonic-response": { status: "ok", starred2: { song, album, artist } },
    }),
  }));
}

describe("StarredView", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    globalThis.fetch = starred();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads everything that was starred", async () => {
    render(StarredView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    expect(globalThis.fetch.mock.calls[0][0]).toContain("/rest/getStarred2?");
    expect(screen.getByText("Close Combat")).toBeTruthy();
    expect(screen.getAllByText("Angerfist").length).toBeGreaterThan(0);
  });

  it("shows how many tracks are starred", async () => {
    render(StarredView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText(/1 nummer/i)).toBeTruthy());
  });

  it("copes with a server that returns single items rather than lists", async () => {
    globalThis.fetch = starred({ song: SONG, album: ALBUM, artist: ARTIST });

    render(StarredView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    expect(screen.getByText("Close Combat")).toBeTruthy();
  });

  it("says so when nothing is starred yet", async () => {
    globalThis.fetch = starred({ song: [], album: [], artist: [] });

    render(StarredView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Nog geen favorieten")).toBeTruthy());
  });

  it("offers no play button when there is nothing to play", async () => {
    globalThis.fetch = starred({ song: [], album: [], artist: [] });

    render(StarredView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Nog geen favorieten")).toBeTruthy());
    expect(screen.queryByTitle("Alles afspelen")).toBeNull();
  });

  it("playing everything queues the starred tracks and starts the first", async () => {
    render(StarredView, { onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByTitle("Alles afspelen")).toBeTruthy());

    await fireEvent.click(screen.getByTitle("Alles afspelen"));

    expect(get(playlist)).toEqual([SONG]);
    expect(get(currentTrack)).toEqual(SONG);
    expect(get(playerState).playing).toBe(true);
  });

  it("opens the album that was clicked", async () => {
    const onnavigate = vi.fn();
    render(StarredView, { onnavigate });
    await waitFor(() => expect(screen.getByText("Close Combat")).toBeTruthy());

    await fireEvent.click(screen.getByText("Close Combat"));

    expect(onnavigate).toHaveBeenCalledWith("album:album-1");
  });

  it("opens the artist that was clicked", async () => {
    const onnavigate = vi.fn();
    render(StarredView, { onnavigate });
    await waitFor(() => expect(screen.getByText("Close Combat")).toBeTruthy());

    const artistButtons = screen
      .getAllByText("Angerfist")
      .map((el) => el.closest("button"))
      .filter(Boolean);
    await fireEvent.click(artistButtons.at(-1));

    expect(onnavigate).toHaveBeenCalledWith("artist:artist-1");
  });

  it("survives a request that never arrives", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });

    render(StarredView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Nog geen favorieten")).toBeTruthy());
  });

  it("survives a server that refuses the request", async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, json: async () => ({}) }));

    render(StarredView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Nog geen favorieten")).toBeTruthy());
  });
});
