/**
 * The whole feed on one page, with a play button.
 *
 * What matters here is the queue: pressing play must load MuMa's order into the player as-is,
 * because that order is the feed. And an empty feed has to say so -- it is a real answer, not a
 * failure, and a blank page under a big heading reads as broken.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

import FeedView from "../../src/lib/FeedView.svelte";
import { entityCache, feedKey } from "../../src/lib/entityLoaders.js";
import { clearSeeds, seedEntity } from "../../src/lib/entitySeeds.js";
import {
  credentials,
  currentTrack,
  queueContinuation,
  isMobile,
  playerState,
  playlist,
  subsonicToken,
} from "../../src/lib/store.js";

const SONGS = [
  { id: "song-1", title: "Raise Your Fist", artist: "Angerfist", suffix: "flac" },
  { id: "song-2", title: "Second", artist: "Someone", suffix: "mp3" },
];

function detailOf(tracks, extra = {}) {
  return {
    state: "ok",
    title: null,
    subtitle: null,
    hardnessBand: null,
    relaxedTo: null,
    filledFromUnknown: null,
    tracks,
    ...extra,
  };
}

/**
 * `streamFeedDetail` told from a `__loadFeedDetail` answer: the header first, then its songs as
 * one chunk whose paths count the unresolved ones too -- what the page needs to say "2 niet
 * gevonden". Tests that care about chunking replace `__streamFeedDetail` with their own.
 */
async function streamFromDetail(slug, auth, handlers = {}) {
  const result = await globalThis.__loadFeedDetail(slug, auth);
  const total = result.tracks.length + (result.unresolved ?? 0);
  const paths = Array.from({ length: total }, (_, i) => `p${i}.mp3`);
  handlers.onHeader?.({ ...result, chunks: total > 0 ? [paths] : [] });
  if (total > 0) handlers.onChunk?.(0, { songs: result.tracks, failed: false });
  return { failedChunks: 0, unresolved: 0, ...result };
}

vi.mock("../../src/lib/feeds.js", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    loadFeedDetail: (...args) => globalThis.__loadFeedDetail(...args),
    streamFeedDetail: (...args) => globalThis.__streamFeedDetail(...args),
    resolveFeedChunk: (...args) => globalThis.__resolveFeedChunk(...args),
    loadFeedPage: (...args) => globalThis.__loadFeedPage(...args),
  };
});

describe("FeedView", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    subsonicToken.set({ username: "user", token: "test-subsonic-token" });
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    globalThis.__loadFeedDetail = vi.fn(async () => detailOf(SONGS));
    globalThis.__streamFeedDetail = vi.fn(streamFromDetail);
    globalThis.__resolveFeedChunk = vi.fn(async () => ({ songs: [], failed: false }));
    entityCache.clear();
    clearSeeds();
    globalThis.__loadFeedPage = vi.fn(async () => ({
      tracks: [],
      nextOffset: null,
      failed: false,
    }));
    queueContinuation.set(null);
    isMobile.set(false);
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the feed it was asked for", async () => {
    render(FeedView, { slug: "release-radar", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    expect(globalThis.__loadFeedDetail.mock.calls[0][0]).toBe("release-radar");
  });

  it("the daily mix asks for the daily mix", async () => {
    render(FeedView, { slug: "daily-mix", onnavigate: vi.fn() });

    await waitFor(() => expect(globalThis.__loadFeedDetail).toHaveBeenCalled());
    expect(globalThis.__loadFeedDetail.mock.calls[0][0]).toBe("daily-mix");
  });

  it("shows a spectrum mix's own slug when asked for one", async () => {
    render(FeedView, { slug: "daily-mix-soft", onnavigate: vi.fn() });

    await waitFor(() => expect(globalThis.__loadFeedDetail).toHaveBeenCalled());
    expect(globalThis.__loadFeedDetail.mock.calls[0][0]).toBe("daily-mix-soft");
  });

  it("queues the feed in MuMa's order and starts it", async () => {
    render(FeedView, { slug: "release-radar", onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());

    await fireEvent.click(screen.getByTitle("Alles afspelen"));

    expect(get(playlist).map((track) => track.id)).toEqual(["song-1", "song-2"]);
    expect(get(currentTrack).id).toBe("song-1");
    expect(get(playerState).playing).toBe(true);
  });

  it("says so when the feed is empty rather than showing an empty list", async () => {
    globalThis.__loadFeedDetail = vi.fn(async () => detailOf([]));

    render(FeedView, { slug: "release-radar", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Hier staat nu niets")).toBeTruthy());
    expect(screen.queryByTitle("Alles afspelen")).toBeNull();
  });

  it("counts what it found", async () => {
    render(FeedView, { slug: "release-radar", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText(/2 nummers/)).toBeTruthy());
  });

  it("shows the server's title and subtitle when it has one", async () => {
    globalThis.__loadFeedDetail = vi.fn(async () =>
      detailOf(SONGS, { title: "Zachter", subtitle: "≤ 42 hardheid" }),
    );

    render(FeedView, { slug: "daily-mix-soft", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Zachter")).toBeTruthy());
    expect(screen.getByText("≤ 42 hardheid")).toBeTruthy();
  });

  it("shows the band and how many places were filled from unknown hardness", async () => {
    globalThis.__loadFeedDetail = vi.fn(async () =>
      detailOf(SONGS, { hardnessBand: [10, 42], filledFromUnknown: 3 }),
    );

    render(FeedView, { slug: "daily-mix-soft", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText(/band 10–42/)).toBeTruthy());
    expect(screen.getByText(/3 aangevuld/)).toBeTruthy();
  });

  it("shows only the band when nothing needed to be filled in", async () => {
    globalThis.__loadFeedDetail = vi.fn(async () =>
      detailOf(SONGS, { hardnessBand: [42, 70], filledFromUnknown: 0 }),
    );

    render(FeedView, { slug: "daily-mix-mid", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText(/band 42–70/)).toBeTruthy());
    expect(screen.queryByText(/aangevuld/)).toBeNull();
  });

  it("shows no band line for a feed that never carries one", async () => {
    render(FeedView, { slug: "release-radar", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    expect(screen.queryByText(/band/)).toBeNull();
  });

  it('offers no "Meer laden" when the feed has nothing more', async () => {
    render(FeedView, { slug: "release-radar", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    expect(screen.queryByText("Meer laden")).toBeNull();
  });

  it("appends the next page without repeating a song, until there is no more", async () => {
    globalThis.__loadFeedDetail = vi.fn(async () => detailOf(SONGS, { nextOffset: 100 }));
    globalThis.__loadFeedPage = vi.fn(async () => ({
      tracks: [SONGS[1], { id: "song-3", title: "Third", artist: "Other", suffix: "mp3" }],
      nextOffset: null,
      failed: false,
    }));

    render(FeedView, { slug: "daily-mix", onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Meer laden")).toBeTruthy());

    await fireEvent.click(screen.getByText("Meer laden"));

    await waitFor(() => expect(screen.getByText("Third")).toBeTruthy());
    expect(globalThis.__loadFeedPage.mock.calls[0][0]).toBe("daily-mix");
    expect(globalThis.__loadFeedPage.mock.calls[0][2]).toBe(100);
    expect(screen.getAllByText("Second")).toHaveLength(1);
    expect(screen.getByText(/3 nummers/)).toBeTruthy();
    expect(screen.queryByText("Meer laden")).toBeNull();
  });

  it("keeps the button after a failed page, so a second tap can try again", async () => {
    globalThis.__loadFeedDetail = vi.fn(async () => detailOf(SONGS, { nextOffset: 100 }));
    globalThis.__loadFeedPage = vi.fn(async () => ({ tracks: [], nextOffset: 100, failed: true }));

    render(FeedView, { slug: "daily-mix", onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Meer laden")).toBeTruthy());
    await fireEvent.click(screen.getByText("Meer laden"));

    await waitFor(() => expect(globalThis.__loadFeedPage).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByText("Meer laden")).toBeTruthy());
  });

  it("starts a queue that knows where the feed continues", async () => {
    globalThis.__loadFeedDetail = vi.fn(async () => detailOf(SONGS, { nextOffset: 100 }));

    render(FeedView, { slug: "daily-mix", onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    await fireEvent.click(screen.getByTitle("Alles afspelen"));

    expect(get(queueContinuation)).toMatchObject({ kind: "feed", slug: "daily-mix", cursor: 100 });
  });

  // Bug report 122. A row tap is how most people start a mix; it used to start a queue without
  // the continuation, so the player never topped it up.
  it("a tapped row starts a queue that continues the feed, like the play button", async () => {
    // A single tap plays a row on the phone and the tablet; the desktop needs a double click.
    isMobile.set(true);
    globalThis.__loadFeedDetail = vi.fn(async () =>
      detailOf(SONGS, { title: "Harder", nextOffset: 100 }),
    );

    render(FeedView, { slug: "daily-mix-hard", onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Second")).toBeTruthy());
    await fireEvent.click(screen.getByText("Second"));

    expect(get(playlist).map((track) => track.id)).toEqual(["song-1", "song-2"]);
    expect(get(currentTrack).id).toBe("song-2");
    expect(get(queueContinuation)).toMatchObject({
      kind: "feed",
      slug: "daily-mix-hard",
      cursor: 100,
    });
  });

  it("a tapped row after the last page starts a queue with nothing to continue", async () => {
    isMobile.set(true);
    render(FeedView, { slug: "daily-mix-hard", onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Second")).toBeTruthy());
    await fireEvent.click(screen.getByText("Second"));

    expect(get(queueContinuation)).toBeNull();
  });

  it("says how many of MuMa's tracks the server could not find, and adds a later page's", async () => {
    globalThis.__loadFeedDetail = vi.fn(async () =>
      detailOf(SONGS, { nextOffset: 100, unresolved: 2 }),
    );
    globalThis.__loadFeedPage = vi.fn(async () => ({
      tracks: [{ id: "song-3", title: "Third", artist: "Other", suffix: "mp3" }],
      nextOffset: 200,
      unresolved: 1,
      failed: false,
    }));

    render(FeedView, { slug: "daily-mix-hard", onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText(/2 niet gevonden op de server/)).toBeTruthy());

    await fireEvent.click(screen.getByText("Meer laden"));

    await waitFor(() => expect(screen.getByText(/3 niet gevonden op de server/)).toBeTruthy());
    // The button stays: MuMa said there is a page after this one.
    expect(screen.getByText("Meer laden")).toBeTruthy();
  });

  it("says nothing about missing tracks when every path resolved", async () => {
    globalThis.__loadFeedDetail = vi.fn(async () => detailOf(SONGS, { unresolved: 0 }));

    render(FeedView, { slug: "daily-mix-hard", onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());

    expect(screen.queryByTestId("feed-unresolved")).toBeNull();
  });

  // The phone and the tablet both run with `isMobile` (bug report 090: a tablet is "mobile" at
  // any width). The button must not depend on the layout.
  for (const layout of ["phone", "tablet"]) {
    it(`offers "Meer laden" under a 98-track list on the ${layout}`, async () => {
      isMobile.set(true);
      const many = Array.from({ length: 98 }, (_, i) => ({
        id: `s${i}`,
        title: `Track ${i}`,
        artist: "A",
        suffix: "mp3",
      }));
      globalThis.__loadFeedDetail = vi.fn(async () =>
        detailOf(many, { nextOffset: 100, unresolved: 2 }),
      );

      render(FeedView, { slug: "daily-mix-hard", onnavigate: vi.fn() });

      await waitFor(() => expect(screen.getByTestId("feed-load-more")).toBeTruthy());
      expect(screen.getByText(/98 nummers/)).toBeTruthy();
    });
  }
});

/**
 * Issue #110: the page opens at once and fills in. The header comes from what the card knew, the
 * rows from each `getSongsByPath` chunk as it lands -- in MuMa's order, whatever order LMS answers
 * in -- and a chunk or a feed that fails gets its own retry rather than a blank page.
 */
describe("FeedView progressive load", () => {
  /** A controllable stream: the test decides when the header and each chunk arrive. */
  function heldStream() {
    const held = {};
    globalThis.__streamFeedDetail = vi.fn(
      (slug, auth, handlers) =>
        new Promise((resolve) => {
          held.handlers = handlers;
          held.resolve = resolve;
        }),
    );
    return held;
  }

  const song = (n) => ({ id: `s${n}`, title: `Track ${n}`, artist: "A", suffix: "mp3" });

  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    subsonicToken.set({ username: "user", token: "test-subsonic-token" });
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    queueContinuation.set(null);
    isMobile.set(false);
    entityCache.clear();
    clearSeeds();
    globalThis.__loadFeedDetail = vi.fn(async () => detailOf(SONGS));
    globalThis.__resolveFeedChunk = vi.fn(async () => ({ songs: [], failed: false }));
    globalThis.__loadFeedPage = vi.fn(async () => ({
      tracks: [],
      nextOffset: null,
      failed: false,
    }));
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
  });

  it("draws the card's title and subtitle and skeleton rows before MuMa has answered", async () => {
    heldStream();
    seedEntity("feed", "daily-mix-soft", { name: "Zachter", subtitle: "≤ 42 hardheid" });

    render(FeedView, { slug: "daily-mix-soft", onnavigate: vi.fn() });

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Zachter");
    expect(screen.getByText("≤ 42 hardheid")).toBeTruthy();
    expect(screen.getByTestId("skeleton-rows")).toBeTruthy();
    expect(screen.queryByText("Laden...")).toBeNull();
  });

  it("draws a skeleton title for a mix opened by URL, with nothing known about it", () => {
    heldStream();

    render(FeedView, { slug: "daily-mix-hard", onnavigate: vi.fn() });

    expect(screen.getByTestId("feed-title-skeleton")).toBeTruthy();
    expect(screen.queryByRole("heading", { level: 1 })).toBeNull();
  });

  it("names the release radar at once from its fixed copy", () => {
    heldStream();

    render(FeedView, { slug: "release-radar", onnavigate: vi.fn() });

    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Release Radar");
    expect(screen.getByTestId("skeleton-rows")).toBeTruthy();
  });

  it("replaces the card's title with the server's once it answers", async () => {
    const held = heldStream();
    seedEntity("feed", "daily-mix-artist", { name: "Old guess" });
    render(FeedView, { slug: "daily-mix-artist", onnavigate: vi.fn() });

    held.handlers.onHeader({ ...detailOf([], { title: "Angerfist" }), chunks: [] });

    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Angerfist"),
    );
  });

  it("shows each chunk in MuMa's order as it lands, with skeletons for the rest", async () => {
    const held = heldStream();
    render(FeedView, { slug: "daily-mix", onnavigate: vi.fn() });
    const first = Array.from({ length: 100 }, (_, i) => `a${i}.mp3`);
    const second = ["b0.mp3", "b1.mp3"];

    held.handlers.onHeader({ ...detailOf([]), chunks: [first, second] });
    // The second chunk answers first: it must not appear above the first.
    held.handlers.onChunk(1, { songs: [song(100), song(101)], failed: false });
    await waitFor(() => expect(screen.getByTestId("skeleton-rows")).toBeTruthy());
    expect(screen.queryByText("Track 100")).toBeNull();

    held.handlers.onChunk(0, { songs: [song(0), song(1)], failed: false });

    await waitFor(() => expect(screen.getByText("Track 100")).toBeTruthy());
    const titles = screen.getAllByText(/^Track \d+$/).map((el) => el.textContent.trim());
    expect(titles).toEqual(["Track 0", "Track 1", "Track 100", "Track 101"]);
    expect(screen.queryByTestId("skeleton-rows")).toBeNull();
    // 102 paths, 4 songs: the unresolved note from bug report 122 still adds up.
    expect(screen.getByTestId("feed-unresolved").textContent).toMatch(/98 niet gevonden/);
  });

  it("draws the first chunk's rows while the second is still on its way", async () => {
    const held = heldStream();
    render(FeedView, { slug: "daily-mix", onnavigate: vi.fn() });

    held.handlers.onHeader({ ...detailOf([]), chunks: [["a.mp3"], ["b.mp3"]] });
    held.handlers.onChunk(0, { songs: [song(0)], failed: false });

    await waitFor(() => expect(screen.getByText("Track 0")).toBeTruthy());
    expect(screen.getByTestId("skeleton-rows")).toBeTruthy();
    // No "Meer laden" before the first page is whole.
    expect(screen.queryByTestId("feed-load-more")).toBeNull();
  });

  it("offers a retry for a chunk LMS failed to answer, and fills it in on retry", async () => {
    const held = heldStream();
    render(FeedView, { slug: "daily-mix", onnavigate: vi.fn() });
    held.handlers.onHeader({ ...detailOf([]), chunks: [["a.mp3"], ["b.mp3"]] });
    held.handlers.onChunk(0, { songs: [song(0)], failed: false });
    held.handlers.onChunk(1, { songs: [], failed: true });

    await waitFor(() => expect(screen.getByTestId("section-error")).toBeTruthy());
    expect(screen.getByText("Track 0")).toBeTruthy();
    expect(screen.queryByTestId("feed-unresolved")).toBeNull();

    globalThis.__resolveFeedChunk = vi.fn(async () => ({ songs: [song(1)], failed: false }));
    await fireEvent.click(screen.getByText("Opnieuw"));

    await waitFor(() => expect(screen.getByText("Track 1")).toBeTruthy());
    expect(globalThis.__resolveFeedChunk.mock.calls[0][0]).toEqual(["b.mp3"]);
    expect(screen.queryByTestId("section-error")).toBeNull();
    // Whole now: a revisit is answered from the cache.
    expect(entityCache.peek(feedKey("daily-mix")).value.tracks.map((t) => t.id)).toEqual([
      "s0",
      "s1",
    ]);
  });

  it("offers a retry when MuMa itself could not be reached", async () => {
    globalThis.__streamFeedDetail = vi.fn(streamFromDetail);
    globalThis.__loadFeedDetail = vi.fn(async () => detailOf([], { state: "error" }));
    render(FeedView, { slug: "daily-mix-hard", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByTestId("section-error")).toBeTruthy());
    expect(screen.queryByText("Hier staat nu niets")).toBeNull();

    globalThis.__loadFeedDetail = vi.fn(async () => detailOf(SONGS));
    await fireEvent.click(screen.getByText("Opnieuw"));

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    expect(globalThis.__streamFeedDetail).toHaveBeenCalledTimes(2);
  });

  it("starts the feed as soon as it is whole when play was pressed while it loaded", async () => {
    const held = heldStream();
    render(FeedView, { slug: "daily-mix", onnavigate: vi.fn() });

    await fireEvent.click(screen.getByTestId("feed-play"));
    expect(screen.getByTestId("throbber")).toBeTruthy();
    expect(get(playlist)).toEqual([]);

    held.handlers.onHeader({ ...detailOf([], { nextOffset: 100 }), chunks: [["a.mp3", "b.mp3"]] });
    held.handlers.onChunk(0, { songs: SONGS, failed: false });

    await waitFor(() => expect(get(playlist).map((t) => t.id)).toEqual(["song-1", "song-2"]));
    expect(get(playerState).playing).toBe(true);
    expect(get(queueContinuation)).toMatchObject({ kind: "feed", slug: "daily-mix", cursor: 100 });
  });

  it("answers a revisit from the cache without asking again", async () => {
    globalThis.__streamFeedDetail = vi.fn(streamFromDetail);
    entityCache.set(feedKey("daily-mix"), { ...detailOf(SONGS), unresolved: 0, failedChunks: 0 });

    render(FeedView, { slug: "daily-mix", onnavigate: vi.fn() });

    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
    expect(screen.queryByTestId("skeleton-rows")).toBeNull();
    expect(globalThis.__streamFeedDetail).not.toHaveBeenCalled();
  });

  it("caches a whole first page after streaming it", async () => {
    globalThis.__streamFeedDetail = vi.fn(streamFromDetail);

    render(FeedView, { slug: "daily-mix", onnavigate: vi.fn() });

    await waitFor(() => expect(entityCache.peek(feedKey("daily-mix"))).not.toBeNull());
  });
});
