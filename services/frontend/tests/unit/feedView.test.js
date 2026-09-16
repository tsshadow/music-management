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
import { credentials, currentTrack, playerState, playlist } from "../../src/lib/store.js";

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
  return { ...actual, loadFeedDetail: (...args) => globalThis.__loadFeedDetail(...args) };
});

describe("FeedView", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    globalThis.__loadFeedDetail = vi.fn(async () => detailOf(SONGS));
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
});
