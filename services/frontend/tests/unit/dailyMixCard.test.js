/**
 * One daily-mix tile: a colour or a cover, and a play button that starts the mix without leaving
 * the shelf it sits on.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

import DailyMixCard from "../../src/lib/DailyMixCard.svelte";
import { entityCache, feedKey } from "../../src/lib/entityLoaders.js";
import { clearSeeds, peekSeed } from "../../src/lib/entitySeeds.js";
import {
  authParams,
  credentials,
  currentTrack,
  queueContinuation,
  playerState,
  playlist,
  subsonicToken,
} from "../../src/lib/store.js";

const SONGS = [{ id: "song-1", title: "Legacy" }];

vi.mock("../../src/lib/feeds.js", async (importOriginal) => {
  const actual = await importOriginal();
  return { ...actual, loadFeedDetail: (...args) => globalThis.__loadFeed(...args) };
});

describe("DailyMixCard", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "demo-user", password: "pw" });
    subsonicToken.set({ username: "demo-user", token: "test-subsonic-token" });
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    globalThis.__loadFeed = vi.fn(async () => ({ state: "ok", tracks: SONGS, nextOffset: 100 }));
    entityCache.clear();
    clearSeeds();
  });

  // Issue #99: on a touchscreen there is no hover to reveal the button. jsdom applies no CSS, so
  // this pins the classes; tests/browser/progressive-feeds.spec.js checks it with the real
  // stylesheet on a touch viewport.
  it("keeps the play button visible on a coarse pointer and reveals it on hover otherwise", () => {
    render(DailyMixCard, { slug: "daily-mix-soft", title: "Zachter" });

    const classes = screen.getByTestId("mix-card-play").className;
    expect(classes).toContain("pointer-coarse:opacity-100");
    expect(classes).toContain("group-hover:opacity-100");
    expect(classes).toContain("focus-visible:opacity-100");
    // A 48px target on a touchscreen, per the style guide.
    expect(classes).toContain("pointer-coarse:w-12");
  });

  it("leaves the mix's title and subtitle for the page it opens", async () => {
    render(DailyMixCard, {
      slug: "daily-mix-soft",
      title: "Zachter",
      subtitle: "≤ 42 hardheid",
      onopen: vi.fn(),
    });

    await fireEvent.click(screen.getByRole("button", { name: /Zachter/ }));

    expect(peekSeed("feed", "daily-mix-soft")).toMatchObject({
      name: "Zachter",
      subtitle: "≤ 42 hardheid",
    });
  });

  it("plays a mix the page already loaded without asking MuMa again", async () => {
    entityCache.set(feedKey("daily-mix-soft"), { state: "ok", tracks: SONGS, nextOffset: 100 });
    render(DailyMixCard, { slug: "daily-mix-soft", title: "Zachter" });

    await fireEvent.click(screen.getByTitle("Alles afspelen"));

    await waitFor(() => expect(get(currentTrack)?.id).toBe("song-1"));
    expect(globalThis.__loadFeed).not.toHaveBeenCalled();
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
