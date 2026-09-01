import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import TrackList from "../../src/lib/TrackList.svelte";
import { credentials, currentTrack, isMobile, playerState, playlist } from "../../src/lib/store.js";

const FIRST = {
  id: "song-1",
  title: "Raise Your Fist",
  artist: "Angerfist",
  artistId: "artist-1",
  duration: 240,
  suffix: "flac",
};
const SECOND = {
  id: "song-2",
  title: "Encore",
  artist: "Angerfist",
  artistId: "artist-1",
  duration: 200,
  suffix: "flac",
};

function props(overrides = {}) {
  return { tracks: [FIRST, SECOND], onnavigate: vi.fn(), ...overrides };
}

function rowAction(title, index = 0) {
  return screen.getAllByTitle(title)[index];
}

// Lets the click's fetch resolve and Svelte flush the resulting render, so an
// assertion sees the state the component settled on and not the one it passed
// through on the way there.
async function settled() {
  await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
  for (let i = 0; i < 3; i++) await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("TrackList", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    playlist.set([FIRST, SECOND]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    isMobile.set(false);
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": { status: "ok", lyricsList: { structuredLyrics: [] } },
      }),
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists the tracks it was given", () => {
    render(TrackList, props());

    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
    expect(screen.getByText("Encore")).toBeTruthy();
  });

  it("playing a track queues the whole list", async () => {
    playlist.set([]);
    render(TrackList, props());

    // On desktop a row plays on its play button or a double click, not a single one.
    await fireEvent.click(screen.getAllByLabelText("Afspelen")[0]);

    expect(get(currentTrack)).toEqual(FIRST);
    expect(get(playlist)).toHaveLength(2);
    expect(get(playerState).playing).toBe(true);
  });

  it("playing from the queue leaves the queue alone", async () => {
    playlist.set([FIRST]);
    render(TrackList, props({ isQueue: true, tracks: [FIRST, SECOND] }));

    await fireEvent.click(screen.getAllByLabelText("Afspelen")[1]);

    expect(get(currentTrack)).toEqual(SECOND);
    expect(get(playlist)).toEqual([FIRST]);
  });

  it("a track can be moved up in the queue", async () => {
    render(TrackList, props({ isQueue: true }));

    await fireEvent.click(rowAction("Omhoog", 1));

    expect(get(playlist).map((t) => t.id)).toEqual(["song-2", "song-1"]);
  });

  it("a track can be moved down in the queue", async () => {
    render(TrackList, props({ isQueue: true }));

    await fireEvent.click(rowAction("Omlaag"));

    expect(get(playlist).map((t) => t.id)).toEqual(["song-2", "song-1"]);
  });

  it("moving past the end of the queue changes nothing", async () => {
    render(TrackList, props({ isQueue: true }));

    await fireEvent.click(rowAction("Omhoog"));

    expect(get(playlist).map((t) => t.id)).toEqual(["song-1", "song-2"]);
  });

  it("a track can be removed from the queue", async () => {
    render(TrackList, props({ isQueue: true }));

    await fireEvent.click(rowAction("Verwijderen"));

    expect(get(playlist).map((t) => t.id)).toEqual(["song-2"]);
  });

  it("removing from a playlist is handed to the parent", async () => {
    const onremove = vi.fn();
    render(TrackList, props({ playlistId: "pl-1", onremove }));

    await fireEvent.click(rowAction("Verwijderen"));

    expect(onremove).toHaveBeenCalledWith(0);
    expect(get(playlist)).toHaveLength(2);
  });

  it("a track can be queued to play next", async () => {
    currentTrack.set(FIRST);
    playlist.set([FIRST]);
    render(TrackList, props({ tracks: [SECOND] }));

    await fireEvent.click(rowAction("Hierna afspelen"));

    expect(get(playlist).map((t) => t.id)).toEqual(["song-1", "song-2"]);
  });

  it("a track can be added to the end of the queue", async () => {
    playlist.set([FIRST]);
    render(TrackList, props({ tracks: [SECOND] }));

    await fireEvent.click(rowAction("Aan wachtrij toevoegen"));

    expect(get(playlist).map((t) => t.id)).toEqual(["song-1", "song-2"]);
  });

  it("rating a track tells the server", async () => {
    render(TrackList, props());

    await fireEvent.click(screen.getAllByLabelText("4 sterren")[0]);

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/rest/setRating"))).toBe(
        true,
      ),
    );
  });

  it("a rating the server accepted stays on screen", async () => {
    const unrated = { ...FIRST, userRating: 0 };
    render(TrackList, props({ tracks: [unrated] }));

    await fireEvent.click(screen.getByLabelText("4 sterren"));
    await settled();

    expect(screen.getByLabelText("4 sterren").className).toContain("text-brand");
  });

  // Subsonic answers errors with HTTP 200 and a "failed" body, so a rating the
  // server refused used to keep its stars lit while nothing was stored.
  it("a rating the server refused does not stay on screen", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": {
          status: "failed",
          error: { code: 60, message: "Wrong username or password." },
        },
      }),
    }));
    const unrated = { ...FIRST, userRating: 0 };
    render(TrackList, props({ tracks: [unrated] }));

    await fireEvent.click(screen.getByLabelText("4 sterren"));
    await settled();

    expect(screen.getByLabelText("4 sterren").className).not.toContain("text-brand");
  });

  it("reloading a track asks the server to re-read it", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.spyOn(window, "alert").mockImplementation(() => {});
    render(TrackList, props());

    await fireEvent.click(rowAction("Verversen"));

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/refresh"))).toBe(true),
    );
  });

  it("a reload that is not confirmed asks the server nothing", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(TrackList, props());

    await fireEvent.click(rowAction("Verversen"));

    expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/refresh"))).toBe(false);
  });

  it("the artist of a track can be opened", async () => {
    const onnavigate = vi.fn();
    render(TrackList, props({ onnavigate }));

    await fireEvent.click(screen.getAllByText("Angerfist")[0]);

    expect(onnavigate).toHaveBeenCalledWith("artist:artist-1");
  });

  it("an empty list renders nothing to play", () => {
    render(TrackList, props({ tracks: [] }));

    expect(screen.queryByText("Raise Your Fist")).toBeNull();
  });
});
