import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import SearchMoreModal from "../../src/lib/SearchMoreModal.svelte";
import {
  activeModal,
  activeView,
  credentials,
  deduplicateEnabled,
  viewMode,
} from "../../src/lib/store.js";

const SONG = {
  id: "song-1",
  title: "Raise Your Fist",
  artist: "Angerfist",
  artistId: "artist-1",
  suffix: "flac",
  // Two files of one song, as the server groups them. The browser no longer decides that
  // from the title -- it applies what muma worked out and sent along.
  workId: 42,
  isCanonical: true,
};
const DUPLICATE = { ...SONG, id: "song-2", suffix: "mp3", bitRate: 192, isCanonical: false };
const UNGROUPED = { ...SONG, id: "song-3", workId: undefined, isCanonical: undefined };
const ARTIST = { id: "artist-1", name: "Angerfist" };
const ALBUM = { id: "album-1", name: "Close Combat", artist: "Angerfist" };

function subsonic({ song = [SONG], artist = [ARTIST], album = [ALBUM] } = {}) {
  return vi.fn(async () => ({
    ok: true,
    json: async () => ({ "subsonic-response": { searchResult3: { song, artist, album } } }),
  }));
}

describe("SearchMoreModal", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    viewMode.set("songs");
    deduplicateEnabled.set(false);
    activeModal.set({ type: "search-results", data: { query: "angerfist", category: "tracks" } });
    activeView.set("home");
    globalThis.fetch = subsonic();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists the tracks for a track search", async () => {
    render(SearchMoreModal, { query: "angerfist", category: "tracks" });

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    expect(globalThis.fetch.mock.calls[0][0]).toContain("songCount=100");
  });

  it("lists the artists for an artist search", async () => {
    render(SearchMoreModal, { query: "angerfist", category: "artists" });

    await waitFor(() => expect(screen.getByText("Angerfist")).toBeTruthy());
    expect(globalThis.fetch.mock.calls[0][0]).toContain("artistCount=100");
  });

  it("lists the albums for an album search", async () => {
    render(SearchMoreModal, { query: "angerfist", category: "albums" });

    await waitFor(() => expect(screen.getByText("Close Combat")).toBeTruthy());
    expect(globalThis.fetch.mock.calls[0][0]).toContain("albumCount=100");
  });

  it("asks for short tracks in song mode", async () => {
    render(SearchMoreModal, { query: "angerfist", category: "tracks" });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(globalThis.fetch.mock.calls[0][0]).toContain("maxDuration=10");
  });

  it("asks for long recordings in set mode", async () => {
    viewMode.set("sets");

    render(SearchMoreModal, { query: "angerfist", category: "tracks" });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(globalThis.fetch.mock.calls[0][0]).toContain("minDuration=10");
  });

  it("collapses the versions of one song when that is switched on", async () => {
    deduplicateEnabled.set(true);
    globalThis.fetch = subsonic({ song: [SONG, DUPLICATE] });

    render(SearchMoreModal, { query: "angerfist", category: "tracks" });

    await waitFor(() => expect(screen.getAllByText("Raise Your Fist")).toHaveLength(1));
  });

  it("keeps two tracks the server has not grouped, however alike they look", async () => {
    // The browser used to fold these together on their title, which is how an official
    // release lost to a rip of it. What is not grouped yet stays visible.
    deduplicateEnabled.set(true);
    globalThis.fetch = subsonic({ song: [UNGROUPED, { ...UNGROUPED, id: "song-4" }] });

    render(SearchMoreModal, { query: "angerfist", category: "tracks" });

    await waitFor(() => expect(screen.getAllByText("Raise Your Fist")).toHaveLength(2));
  });

  it("keeps duplicates when that is switched off", async () => {
    globalThis.fetch = subsonic({ song: [SONG, DUPLICATE] });

    render(SearchMoreModal, { query: "angerfist", category: "tracks" });

    await waitFor(() => expect(screen.getAllByText("Raise Your Fist")).toHaveLength(2));
  });

  it("opening an album closes the modal and navigates there", async () => {
    render(SearchMoreModal, { query: "angerfist", category: "albums" });
    await waitFor(() => expect(screen.getByText("Close Combat")).toBeTruthy());

    await fireEvent.click(screen.getByText("Close Combat"));

    expect(get(activeView)).toBe("album:album-1");
    expect(get(activeModal)).toBeNull();
  });

  it("opening an artist closes the modal and navigates there", async () => {
    render(SearchMoreModal, { query: "angerfist", category: "artists" });
    await waitFor(() => expect(screen.getByText("Angerfist")).toBeTruthy());

    await fireEvent.click(screen.getByText("Angerfist"));

    expect(get(activeView)).toBe("artist:artist-1");
    expect(get(activeModal)).toBeNull();
  });

  it("survives a search that never arrives", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });

    render(SearchMoreModal, { query: "angerfist", category: "tracks" });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByText("Raise Your Fist")).toBeNull();
  });

  it("a search that finds nothing shows nothing", async () => {
    globalThis.fetch = subsonic({ song: [], artist: [], album: [] });

    render(SearchMoreModal, { query: "zzzz", category: "tracks" });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByText("Raise Your Fist")).toBeNull();
  });
});
