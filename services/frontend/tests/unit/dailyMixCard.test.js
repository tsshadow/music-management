/**
 * One daily-mix tile: a colour or a cover, and a play button that starts the mix without leaving
 * the shelf it sits on.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

import DailyMixCard from "../../src/lib/DailyMixCard.svelte";
import {
  authParams,
  credentials,
  currentTrack,
  queueContinuation,
  playerState,
  playlist,
} from "../../src/lib/store.js";

const SONGS = [{ id: "song-1", title: "Legacy" }];

vi.mock("../../src/lib/feeds.js", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, loadFeedDetail: (...args) => globalThis.__loadFeed(...args) };
});

describe("DailyMixCard", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    globalThis.__loadFeed = vi.fn(async () => ({ state: "ok", tracks: SONGS, nextOffset: 100 }));
  });

  it("shows the title and subtitle it was given", () => {
    render(DailyMixCard, { slug: "daily-mix-soft", title: "Zachter", subtitle: "≤ 42 hardheid" });

    expect(screen.getByText("Zachter")).toBeTruthy();
    expect(screen.getByText("≤ 42 hardheid")).toBeTruthy();
  });

  it("draws the given colour when there is no cover", () => {
    render(DailyMixCard, { slug: "daily-mix-soft", title: "Zachter", color: "#1DB954" });

    expect(screen.getByRole("button", { name: /Zachter/ }).style.backgroundColor).toBe(
      "rgb(29, 185, 84)",
    );
  });

  it("draws the cover instead of the colour when one is given", () => {
    render(DailyMixCard, {
      slug: "daily-mix-artist",
      title: "Angerfist",
      cover: "https://muma.example/a.jpg",
    });

    expect(screen.getByRole("button", { name: /Angerfist/ }).getAttribute("style")).toContain(
      'background-image: url("https://muma.example/a.jpg")',
    );
  });

  it("opens the mix's own page when the tile is tapped", async () => {
    const onopen = vi.fn();
    render(DailyMixCard, { slug: "daily-mix-soft", title: "Zachter", onopen });

    await fireEvent.click(screen.getByRole("button", { name: /Zachter/ }));

    expect(onopen).toHaveBeenCalledWith("daily-mix-soft");
  });

  it("plays the mix from the tile's own button without opening the page", async () => {
    const onopen = vi.fn();
    render(DailyMixCard, { slug: "daily-mix-soft", title: "Zachter", onopen });

    await fireEvent.click(screen.getByTitle("Alles afspelen"));

    await waitFor(() => expect(get(playlist).map((t) => t.id)).toEqual(["song-1"]));
    expect(get(currentTrack).id).toBe("song-1");
    expect(get(playerState).playing).toBe(true);
    expect(onopen).not.toHaveBeenCalled();
    expect(globalThis.__loadFeed.mock.calls[0][0]).toBe("daily-mix-soft");
    expect(globalThis.__loadFeed.mock.calls[0][1]).toBe(get(authParams));
    // The queue remembers where the mix continues, so it can top itself up.
    expect(get(queueContinuation)).toMatchObject({
      kind: "feed",
      slug: "daily-mix-soft",
      cursor: 100,
    });
  });
});
