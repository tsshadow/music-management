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

vi.mock("../../src/lib/feeds.js", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    loadFeedDetail: (...args) => globalThis.__loadFeedDetail(...args),
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
