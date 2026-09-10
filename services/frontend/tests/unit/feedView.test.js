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

vi.mock("../../src/lib/feeds.js", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, loadFeed: (...args) => globalThis.__loadFeed(...args) };
});

describe("FeedView", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    globalThis.__loadFeed = vi.fn(async () => SONGS);
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the feed it was asked for", async () => {
    render(FeedView, { slug: "release-radar", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    expect(globalThis.__loadFeed.mock.calls[0][0]).toBe("release-radar");
  });

  it("the daily mix asks for the daily mix", async () => {
    render(FeedView, { slug: "daily-mix", onnavigate: vi.fn() });

    await waitFor(() => expect(globalThis.__loadFeed).toHaveBeenCalled());
    expect(globalThis.__loadFeed.mock.calls[0][0]).toBe("daily-mix");
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
    globalThis.__loadFeed = vi.fn(async () => []);

    render(FeedView, { slug: "release-radar", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Hier staat nu niets")).toBeTruthy());
    expect(screen.queryByTitle("Alles afspelen")).toBeNull();
  });

  it("counts what it found", async () => {
    render(FeedView, { slug: "release-radar", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText(/2 nummers/)).toBeTruthy());
  });
});
