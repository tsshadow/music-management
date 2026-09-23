import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import AlbumView from "../../src/lib/AlbumView.svelte";
import { credentials, currentTrack, playerState, playlist, viewMode } from "../../src/lib/store.js";

const SHORT_TRACK = {
  id: "song-1",
  title: "Raise Your Fist",
  artistId: "artist-1",
  duration: 240,
  discNumber: 1,
};
const SECOND_DISC = {
  id: "song-2",
  title: "Encore",
  artistId: "artist-1",
  duration: 200,
  discNumber: 2,
};
const LONG_SET = {
  id: "set-1",
  title: "Live at Defqon",
  artistId: "artist-1",
  duration: 3600,
  discNumber: 1,
};

function album(overrides = {}) {
  return {
    id: "album-1",
    name: "Close Combat",
    artist: "Angerfist",
    artistId: "artist-1",
    year: 2024,
    coverArt: "cover-1",
    song: [SHORT_TRACK],
    ...overrides,
  };
}

function subsonic({
  albumData = album(),
  info = { notes: "Een klassieker." },
  starOk = true,
} = {}) {
  return vi.fn(async (url) => {
    if (url.includes("/rest/getAlbumInfo2")) {
      return {
        ok: true,
        json: async () => ({ "subsonic-response": { status: "ok", albumInfo: info } }),
      };
    }
    if (url.includes("/rest/getAlbum")) {
      return {
        ok: true,
        json: async () => ({ "subsonic-response": { status: "ok", album: albumData } }),
      };
    }
    return { ok: starOk, json: async () => ({ "subsonic-response": { status: "ok" } }) };
  });
}

async function renderLoaded(props = {}) {
  const rendered = render(AlbumView, { albumId: "album-1", onnavigate: vi.fn(), ...props });
  await waitFor(() => expect(screen.getByText("Close Combat")).toBeTruthy());
  return rendered;
}

describe("AlbumView", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    viewMode.set("songs");
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    globalThis.fetch = subsonic();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the album with its year and track count", async () => {
    await renderLoaded();

    expect(screen.getByText("Angerfist")).toBeTruthy();
    expect(screen.getByText(/2024/)).toBeTruthy();
    expect(screen.getByText(/1 nummer/i)).toBeTruthy();
  });

  it("shows the tracks of the album", async () => {
    await renderLoaded();

    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
  });

  it("copes with a server that returns a single track rather than a list", async () => {
    globalThis.fetch = subsonic({ albumData: album({ song: SHORT_TRACK }) });

    await renderLoaded();

    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
  });

  it("leaves out long recordings in song mode", async () => {
    globalThis.fetch = subsonic({ albumData: album({ song: [SHORT_TRACK, LONG_SET] }) });

    await renderLoaded();

    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
    expect(screen.queryByText("Live at Defqon")).toBeNull();
  });

  it("shows only long recordings in set mode", async () => {
    viewMode.set("sets");
    globalThis.fetch = subsonic({ albumData: album({ song: [SHORT_TRACK, LONG_SET] }) });

    await renderLoaded();

    expect(screen.getByText("Live at Defqon")).toBeTruthy();
    expect(screen.queryByText("Raise Your Fist")).toBeNull();
  });

  it("groups the tracks per disc when there is more than one", async () => {
    globalThis.fetch = subsonic({ albumData: album({ song: [SHORT_TRACK, SECOND_DISC] }) });

    await renderLoaded();

    expect(screen.getByText("Disc 1")).toBeTruthy();
    expect(screen.getByText("Disc 2")).toBeTruthy();
  });

  it("uses the disc titles the server supplies", async () => {
    globalThis.fetch = subsonic({
      albumData: album({
        song: [SHORT_TRACK, SECOND_DISC],
        discTitles: [{ disc: 2, title: "Bonus Disc" }],
      }),
    });

    await renderLoaded();

    expect(screen.getByText("Bonus Disc")).toBeTruthy();
  });

  it("does not label the disc when there is only one", async () => {
    await renderLoaded();

    expect(screen.queryByText("Disc 1")).toBeNull();
  });

  it("playing the album queues every track and starts the first", async () => {
    globalThis.fetch = subsonic({ albumData: album({ song: [SHORT_TRACK, SECOND_DISC] }) });
    const { container } = await renderLoaded();

    await fireEvent.click(container.querySelector(".bg-brand.rounded-full"));

    expect(get(currentTrack)).toEqual(SHORT_TRACK);
    expect(get(playlist)).toHaveLength(2);
    expect(get(playerState).playing).toBe(true);
  });

  it("starring the album tells the server", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByTitle("Toevoegen aan favorieten"));

    await waitFor(() =>
      expect(
        globalThis.fetch.mock.calls.some(([url]) => url.includes("/rest/star?albumId=album-1")),
      ).toBe(true),
    );
  });

  it("unstarring an album that is starred tells the server", async () => {
    globalThis.fetch = subsonic({ albumData: album({ starred: "2026-01-01T01:00:00Z" }) });
    await renderLoaded();

    await fireEvent.click(screen.getByTitle("Verwijderen uit favorieten"));

    await waitFor(() =>
      expect(
        globalThis.fetch.mock.calls.some(([url]) => url.includes("/rest/unstar?albumId=album-1")),
      ).toBe(true),
    );
  });

  it("a star the server refuses is rolled back", async () => {
    globalThis.fetch = subsonic({ starOk: false });
    await renderLoaded();

    await fireEvent.click(screen.getByTitle("Toevoegen aan favorieten"));

    await waitFor(() => expect(screen.getByTitle("Toevoegen aan favorieten")).toBeTruthy());
  });

  it("opens the artist of the album", async () => {
    const onnavigate = vi.fn();
    await renderLoaded({ onnavigate });

    await fireEvent.click(screen.getByText("Angerfist"));

    expect(onnavigate).toHaveBeenCalledWith("artist:artist-1");
  });

  it("an artist the server gave no id for is not a link", async () => {
    globalThis.fetch = subsonic({ albumData: album({ artistId: null }) });
    const onnavigate = vi.fn();
    await renderLoaded({ onnavigate });

    await fireEvent.click(screen.getByText("Angerfist"));

    expect(onnavigate).not.toHaveBeenCalled();
  });

  it("survives a request that never arrives", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });

    render(AlbumView, { albumId: "album-1", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.queryByText("Laden...")).toBeNull());
  });
});

describe("AlbumView - failures", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows an error, not a blank page, when the album cannot be loaded", async () => {
    credentials.set({ url: "", username: "user", password: "pw" });
    vi.spyOn(console, "error").mockImplementation(() => {});
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": { status: "failed", error: { code: 70, message: "Not found" } },
      }),
    }));

    render(AlbumView, { albumId: "gone", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
  });
});
