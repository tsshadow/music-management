import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import ArtistView from "../../src/lib/ArtistView.svelte";
import {
  credentials,
  currentTrack,
  deduplicateEnabled,
  playerState,
  playlist,
  viewMode,
  subsonicToken,
} from "../../src/lib/store.js";
import { recentPlaces, clearRecentPlaces } from "../../src/lib/recentPlaces.js";
import { entityCache } from "../../src/lib/entityLoaders.js";
import { clearSeeds, seedEntity } from "../../src/lib/entitySeeds.js";

const OWN_ALBUM = {
  id: "album-1",
  name: "Close Combat",
  artist: "Angerfist",
  releaseTypes: ["Album"],
};
const OWN_EP = {
  id: "album-2",
  name: "Raise Your Fist",
  artist: "Angerfist",
  releaseTypes: ["EP"],
};
const GUEST_ALBUM = { id: "album-3", name: "Various Hardcore", artist: "Various Artists" };
const TRACK = {
  id: "song-1",
  title: "Raise Your Fist",
  artist: "Angerfist",
  duration: 240,
  suffix: "flac",
};

function artist(overrides = {}) {
  return { id: "artist-1", name: "Angerfist", album: [OWN_ALBUM], ...overrides };
}

function subsonic({
  artistData = artist(),
  tracks = { track: [TRACK], moreResults: false, nextOffset: 1 },
  info = {
    biography: "Hardcore uit Amsterdam.",
    similarArtist: [{ id: "artist-2", name: "Outsiders" }],
  },
  muma = { genre_rules: [{ genre_id: 12, name: "Hardcore", created_by: "user" }] },
  starOk = true,
} = {}) {
  return vi.fn(async (url) => {
    if (url.includes("/rest/getArtistInfo2")) {
      return {
        ok: true,
        json: async () => ({ "subsonic-response": { status: "ok", artistInfo2: info } }),
      };
    }
    if (url.includes("/rest/getSpotifyTracks")) {
      return { ok: true, json: async () => ({ "subsonic-response": { status: "ok", tracks } }) };
    }
    if (url.includes("/rest/getArtist?")) {
      return {
        ok: true,
        json: async () => ({ "subsonic-response": { status: "ok", artist: artistData } }),
      };
    }
    // The curation endpoint, keyed by name. The previous version of this mock
    // answered /api/artists/{id} -- a route that has never existed, so the test
    // passed while the chips on the real page stayed empty.
    if (url.includes("/api/curation/artists/")) {
      return { ok: true, json: async () => muma };
    }
    return { ok: starOk, json: async () => ({ "subsonic-response": { status: "ok" } }) };
  });
}

async function renderLoaded(props = {}) {
  const rendered = render(ArtistView, { artistId: "artist-1", onnavigate: vi.fn(), ...props });
  // The heading, not any "Angerfist": the track rows name the artist too, and they now load
  // alongside the artist rather than after it. "Loaded" means every section has answered.
  await waitFor(() =>
    expect(screen.getByRole("heading", { level: 1, name: "Angerfist" })).toBeTruthy(),
  );
  await waitFor(() => expect(screen.queryByTestId("skeleton-rows")).toBeNull());
  return rendered;
}

describe("ArtistView", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    subsonicToken.set({ username: "user", token: "test-subsonic-token" });
    viewMode.set("songs");
    deduplicateEnabled.set(false);
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    globalThis.fetch = subsonic();
    clearRecentPlaces();
    // Every test answers for the same ids with different data; nothing carries over.
    entityCache.clear();
    clearSeeds();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the artist with their biography", async () => {
    await renderLoaded();

    await waitFor(() => expect(screen.getByText(/Hardcore uit Amsterdam/)).toBeTruthy());
  });

  it("shows the genres the management API knows about", async () => {
    await renderLoaded();

    await waitFor(() => expect(screen.getByText("Hardcore")).toBeTruthy());
  });

  it("groups the releases by their type", async () => {
    globalThis.fetch = subsonic({ artistData: artist({ album: [OWN_ALBUM, OWN_EP] }) });

    await renderLoaded();

    expect(screen.getByText("Albums")).toBeTruthy();
    expect(screen.getByText("EPs")).toBeTruthy();
  });

  it("a release without a type counts as an album", async () => {
    globalThis.fetch = subsonic({
      artistData: artist({ album: [{ id: "album-9", name: "Untyped", artist: "Angerfist" }] }),
    });

    await renderLoaded();

    expect(screen.getByText("Albums")).toBeTruthy();
  });

  it("releases by someone else are listed separately", async () => {
    globalThis.fetch = subsonic({ artistData: artist({ album: [OWN_ALBUM, GUEST_ALBUM] }) });

    await renderLoaded();

    expect(screen.getByText("Various Hardcore")).toBeTruthy();
  });

  it("copes with a server that returns a single album rather than a list", async () => {
    globalThis.fetch = subsonic({ artistData: artist({ album: OWN_ALBUM }) });

    await renderLoaded();

    expect(screen.getByText("Close Combat")).toBeTruthy();
  });

  it("an artist without releases shows none", async () => {
    globalThis.fetch = subsonic({ artistData: artist({ album: undefined }) });

    await renderLoaded();

    expect(screen.queryByText("Close Combat")).toBeNull();
  });

  it("opens the release that was clicked", async () => {
    const onnavigate = vi.fn();
    await renderLoaded({ onnavigate });

    await fireEvent.click(screen.getByText("Close Combat"));

    expect(onnavigate).toHaveBeenCalledWith("album:album-1");
  });

  it("opens a similar artist that was clicked", async () => {
    const onnavigate = vi.fn();
    await renderLoaded({ onnavigate });
    await waitFor(() => expect(screen.getByText("Outsiders")).toBeTruthy());

    await fireEvent.click(screen.getByText("Outsiders"));

    expect(onnavigate).toHaveBeenCalledWith("artist:artist-2");
  });

  it("asks for short tracks in song mode", async () => {
    await renderLoaded();

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("maxDuration=10"))).toBe(
        true,
      ),
    );
  });

  it("asks for long recordings in set mode", async () => {
    viewMode.set("sets");

    await renderLoaded();

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("minDuration=10"))).toBe(
        true,
      ),
    );
  });

  it("asks the server to deduplicate when that is switched on", async () => {
    deduplicateEnabled.set(true);

    await renderLoaded();

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("deduplicate=true"))).toBe(
        true,
      ),
    );
  });

  it("shows the tracks it loaded", async () => {
    await renderLoaded();

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
  });

  it("playing the artist queues their tracks", async () => {
    const { container } = await renderLoaded();
    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());

    await fireEvent.click(container.querySelector(".bg-brand.rounded-full"));

    expect(get(currentTrack)).toEqual(TRACK);
    expect(get(playerState).playing).toBe(true);
  });

  it("starring the artist tells the server", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByTitle("Toevoegen aan favorieten"));

    await waitFor(() =>
      expect(
        globalThis.fetch.mock.calls.some(([url]) => url.includes("/rest/star?artistId=artist-1")),
      ).toBe(true),
    );
  });

  it("unstarring an artist that is starred tells the server", async () => {
    globalThis.fetch = subsonic({ artistData: artist({ starred: "2026-01-01T01:00:00Z" }) });
    await renderLoaded();

    await fireEvent.click(screen.getByTitle("Verwijderen uit favorieten"));

    await waitFor(() =>
      expect(
        globalThis.fetch.mock.calls.some(([url]) => url.includes("/rest/unstar?artistId=artist-1")),
      ).toBe(true),
    );
  });

  it("a star the server refuses is rolled back", async () => {
    globalThis.fetch = subsonic({ starOk: false });
    await renderLoaded();

    await fireEvent.click(screen.getByTitle("Toevoegen aan favorieten"));

    await waitFor(() => expect(screen.getByTitle("Toevoegen aan favorieten")).toBeTruthy());
  });

  it("an artist without extra information still renders", async () => {
    globalThis.fetch = subsonic({ info: null });

    await renderLoaded();

    expect(screen.queryByText("Outsiders")).toBeNull();
  });

  it("survives a request that never arrives", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });

    render(ArtistView, { artistId: "artist-1", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.queryByText("Laden...")).toBeNull());
  });

  // E: the place is opened by id before its name is known; this is the load that backfills it.
  it("records the recent place once the artist's name has loaded", async () => {
    await renderLoaded();

    await waitFor(() => {
      const place = get(recentPlaces).find((p) => p.view === "artist:artist-1");
      expect(place?.title).toBe("Angerfist");
    });
  });
});

/**
 * Going from one artist straight to another reused the same component, nothing guarded against
 * the first artist's answer arriving last, and the biography, similar artists and MusicBrainz id
 * were only cleared when the answer had no info block at all -- so B's page could show A.
 */
describe("ArtistView - switching artists", () => {
  const A = { id: "artist-a", name: "Angerfist", album: [] };
  const B = { id: "artist-b", name: "Miss K8", album: [] };

  /**
   * A server knowing A and B. `holdA`, when given, keeps A's getArtist answer back until it
   * resolves; `infoA`/`infoB` are their getArtistInfo2 blocks.
   */
  function twoArtists({ holdA = null, infoA = { biography: "Bio van A." }, infoB = {} } = {}) {
    const ok = (payload) => ({
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok", ...payload } }),
    });
    return vi.fn(async (url) => {
      const id = new URL(url, "https://lms.example").searchParams.get("id");
      if (url.includes("/rest/getArtist?")) {
        if (id === A.id && holdA) await holdA;
        return ok({ artist: id === A.id ? A : B });
      }
      if (url.includes("/rest/getArtistInfo2"))
        return ok({ artistInfo2: id === A.id ? infoA : infoB });
      if (url.includes("/rest/getSpotifyTracks"))
        return ok({ tracks: { track: [], moreResults: false } });
      if (url.includes("/api/curation/artists/")) return { ok: true, json: async () => ({}) };
      return ok({});
    });
  }

  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    subsonicToken.set({ username: "user", token: "test-subsonic-token" });
    viewMode.set("songs");
    deduplicateEnabled.set(false);
    clearRecentPlaces();
    // Every test answers for the same ids with different data; nothing carries over.
    entityCache.clear();
    clearSeeds();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows B when A's answer arrives after B's", async () => {
    let releaseA;
    const holdA = new Promise((resolve) => {
      releaseA = resolve;
    });
    globalThis.fetch = twoArtists({ holdA });

    const { rerender } = render(ArtistView, { artistId: A.id, onnavigate: vi.fn() });
    await rerender({ artistId: B.id });
    await waitFor(() => expect(screen.getByText(B.name)).toBeTruthy());

    releaseA();
    await new Promise((resolve) => setTimeout(resolve, 20));

    expect(screen.getByText(B.name)).toBeTruthy();
    expect(screen.queryByText(A.name)).toBeNull();
  });

  it("does not keep a biography A had and B lacks", async () => {
    globalThis.fetch = twoArtists();

    const { rerender } = render(ArtistView, { artistId: A.id, onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText(/Bio van A/)).toBeTruthy());

    await rerender({ artistId: B.id });
    await waitFor(() => expect(screen.getByText(B.name)).toBeTruthy());

    expect(screen.queryByText(/Bio van A/)).toBeNull();
  });

  it("shows an error, not a blank page, when the artist cannot be loaded", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": { status: "failed", error: { code: 70, message: "Not found" } },
      }),
    }));

    render(ArtistView, { artistId: "gone", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
  });
});

/**
 * Optimistic navigation (docs/designs/perceived-performance/): the page draws what the link knew
 * at once, starts its requests together, and loads, fails and retries per section.
 */
describe("ArtistView - optimistic page", () => {
  /** A server whose getArtist answer is held back until `release()` is called. */
  function heldArtist({ info = { biography: "Hardcore uit Amsterdam." }, infoFails = false } = {}) {
    let release;
    const held = new Promise((resolve) => {
      release = resolve;
    });
    const ok = (payload) => ({
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok", ...payload } }),
    });
    const fetchMock = vi.fn(async (url) => {
      if (url.includes("/rest/getArtist?")) {
        await held;
        return ok({ artist: artist() });
      }
      if (url.includes("/rest/getArtistInfo2")) {
        if (infoFails) throw new Error("info down");
        return ok({ artistInfo2: info });
      }
      if (url.includes("/rest/getSpotifyTracks"))
        return ok({ tracks: { track: [TRACK], moreResults: false } });
      if (url.includes("/api/curation/artists/")) return { ok: true, json: async () => ({}) };
      return ok({});
    });
    return { fetchMock, release: () => release() };
  }

  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    viewMode.set("songs");
    deduplicateEnabled.set(false);
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    clearRecentPlaces();
    entityCache.clear();
    clearSeeds();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("draws the name the link knew before the server has answered", async () => {
    const { fetchMock } = heldArtist();
    globalThis.fetch = fetchMock;
    seedEntity("artist", "artist-1", { name: "Angerfist" });

    render(ArtistView, { artistId: "artist-1", onnavigate: vi.fn() });

    expect(screen.getByRole("heading", { level: 1, name: "Angerfist" })).toBeTruthy();
    // The releases are still on their way.
    expect(screen.getByTestId("artist-releases-skeleton")).toBeTruthy();
  });

  it("draws a skeleton header when nothing is known about the artist yet", () => {
    const { fetchMock } = heldArtist();
    globalThis.fetch = fetchMock;

    render(ArtistView, { artistId: "artist-1", onnavigate: vi.fn() });

    expect(screen.getByTestId("artist-name-skeleton")).toBeTruthy();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("asks for the tracks without waiting for the artist", async () => {
    const { fetchMock } = heldArtist();
    globalThis.fetch = fetchMock;
    seedEntity("artist", "artist-1", { name: "Angerfist" });

    render(ArtistView, { artistId: "artist-1", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    const urls = fetchMock.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.includes("/rest/getSpotifyTracks"))).toBe(true);
    expect(urls.some((url) => url.includes("/rest/getArtistInfo2"))).toBe(true);
  });

  it("the server's name replaces a wrong one from the link", async () => {
    const { fetchMock, release } = heldArtist();
    globalThis.fetch = fetchMock;
    seedEntity("artist", "artist-1", { name: "Angerfist, Outsiders" });

    render(ArtistView, { artistId: "artist-1", onnavigate: vi.fn() });
    expect(screen.getByRole("heading", { level: 1, name: "Angerfist, Outsiders" })).toBeTruthy();
    release();

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: "Angerfist" })).toBeTruthy(),
    );
  });

  it("keeps the tracks when the similar-artists call fails", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { fetchMock, release } = heldArtist({ infoFails: true });
    globalThis.fetch = fetchMock;
    release();

    render(ArtistView, { artistId: "artist-1", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    expect(screen.getByRole("heading", { level: 1, name: "Angerfist" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a retry for the tracks alone when only they fail, and retrying loads them", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    let tracksDown = true;
    globalThis.fetch = vi.fn(async (url) => {
      if (url.includes("/rest/getSpotifyTracks") && tracksDown) throw new Error("tracks down");
      return subsonic()(url);
    });

    render(ArtistView, { artistId: "artist-1", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByTestId("section-error")).toBeTruthy());
    expect(screen.getByRole("heading", { level: 1, name: "Angerfist" })).toBeTruthy();
    tracksDown = false;
    await fireEvent.click(screen.getByRole("button", { name: "Opnieuw" }));
    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
  });

  it("play pressed while the tracks load waits for them, then plays", async () => {
    let releaseTracks;
    const tracksHeld = new Promise((resolve) => {
      releaseTracks = resolve;
    });
    globalThis.fetch = vi.fn(async (url) => {
      if (url.includes("/rest/getSpotifyTracks")) await tracksHeld;
      return subsonic()(url);
    });

    render(ArtistView, { artistId: "artist-1", onnavigate: vi.fn() });
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: "Angerfist" })).toBeTruthy(),
    );
    await fireEvent.click(screen.getByRole("button", { name: "Afspelen" }));
    expect(screen.getByTestId("throbber")).toBeTruthy();
    expect(get(currentTrack)).toBeNull();

    releaseTracks();

    await waitFor(() => expect(get(currentTrack)?.id).toBe("song-1"));
    expect(get(playerState).playing).toBe(true);
    expect(screen.queryByTestId("throbber")).toBeNull();
  });

  it("a revisit renders from the cache without waiting for the server", async () => {
    globalThis.fetch = subsonic();
    const first = render(ArtistView, { artistId: "artist-1", onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    first.unmount();

    const { fetchMock } = heldArtist();
    globalThis.fetch = fetchMock;
    render(ArtistView, { artistId: "artist-1", onnavigate: vi.fn() });

    expect(screen.getByRole("heading", { level: 1, name: "Angerfist" })).toBeTruthy();
    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
    expect(screen.queryByTestId("skeleton-rows")).toBeNull();
  });
});
