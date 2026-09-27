/**
 * Lists that continue in the queue (docs/designs/list-continuation/, issue #100): "Nummers ·
 * Recent uitgebracht", a filtered song list and a preset each have "Meer laden" on the page, hand
 * the queue they start a continuation, show the same pill under the queue, top the queue up near
 * its end, and end in "Einde van de lijst" once the source is exhausted.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

import Dashboard from "../../src/lib/Dashboard.svelte";
import PresetView from "../../src/lib/PresetView.svelte";
import QueueLoadMore from "../../src/lib/QueueLoadMore.svelte";
import { extendQueue } from "../../src/lib/listContinuation.js";
import { resetFeedsCache } from "../../src/lib/feeds.js";
import { normalizePreset } from "../../src/lib/presets.js";
import { startQueue } from "../../src/lib/queue.js";
import {
  activeView,
  credentials,
  currentTrack,
  deduplicateEnabled,
  favoriteGenres,
  isMobile,
  memoriesOnHomeEnabled,
  playlist,
  queueContinuation,
  trackPageSize,
  viewMode,
  subsonicToken,
} from "../../src/lib/store.js";

const track = (id) => ({
  id,
  title: `Title ${id}`,
  artist: "Angerfist",
  duration: 200,
  suffix: "mp3",
});

/** Five tracks in pages of two: offset 0, 2 and 4, the last one short. */
const TRACK_PAGES = {
  0: { track: [track("a"), track("b")], moreResults: true, nextOffset: 2 },
  2: { track: [track("c"), track("d")], moreResults: true, nextOffset: 4 },
  4: { track: [track("e")], moreResults: false, nextOffset: 5 },
};

function lms() {
  return vi.fn(async (url) => {
    const text = String(url);
    if (text.includes("/rest/getSpotifyTracks")) {
      const offset = Number(new URL(text, "http://x").searchParams.get("offset"));
      const tracks = TRACK_PAGES[offset] ?? { track: [], moreResults: false };
      return { ok: true, json: async () => ({ "subsonic-response": { status: "ok", tracks } }) };
    }
    if (text.includes("/rest/getSongs?")) {
      const params = new URL(text, "http://x").searchParams;
      const offset = Number(params.get("offset"));
      const song = offset === 0 ? [track("p1"), track("p2")] : [track("p3")];
      return {
        ok: true,
        json: async () => ({ "subsonic-response": { status: "ok", songs: { song } } }),
      };
    }
    if (text.endsWith("/api/feeds")) return { ok: true, json: async () => ({ feeds: [] }) };
    return { ok: true, json: async () => ({ "subsonic-response": { status: "ok" } }) };
  });
}

function spotifyTrackUrls() {
  return globalThis.fetch.mock.calls
    .map(([url]) => String(url))
    .filter((url) => url.includes("/rest/getSpotifyTracks"));
}

const queueIds = () => get(playlist).map((t) => t.id);

beforeEach(() => {
  credentials.set({ url: "", username: "user", password: "pw" });
  subsonicToken.set({ username: "user", token: "test-subsonic-token" });
  viewMode.set("songs");
  deduplicateEnabled.set(false);
  favoriteGenres.set([]);
  memoriesOnHomeEnabled.set(false);
  trackPageSize.set(2);
  isMobile.set(false);
  currentTrack.set(null);
  startQueue([], { view: null });
  resetFeedsCache();
  // The songs list loads its next page when the pill scrolls into view; never here.
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  globalThis.fetch = lms();
});

afterEach(() => {
  vi.unstubAllGlobals();
  trackPageSize.set(50);
  activeView.set("home");
});

describe("Nummers · Recent uitgebracht", () => {
  it("continues on the page and ends there with 'Einde van de lijst'", async () => {
    render(Dashboard, { activeView: "songs" });
    await waitFor(() => expect(screen.getByText("Title a")).toBeTruthy());

    await fireEvent.click(screen.getByTestId("tracks-load-more"));
    await waitFor(() => expect(screen.getByText("Title d")).toBeTruthy());
    await fireEvent.click(screen.getByTestId("tracks-load-more"));
    await waitFor(() => expect(screen.getByText("Title e")).toBeTruthy());

    expect(screen.queryByTestId("tracks-load-more")).toBeNull();
    expect(screen.getByText("Einde van de lijst")).toBeTruthy();
  });

  it("a row starts a queue that shows 'Meer laden', tops up near its end, and ends", async () => {
    activeView.set("songs");
    render(Dashboard, { activeView: "songs" });
    await waitFor(() => expect(screen.getAllByLabelText("Afspelen").length).toBe(2));

    await fireEvent.click(screen.getAllByLabelText("Afspelen")[0]);

    expect(queueIds()).toEqual(["a", "b"]);
    expect(get(queueContinuation)).toMatchObject({ kind: "songs", cursor: 2, exhausted: false });

    // The queue's own pill fetches the next page at once.
    render(QueueLoadMore);
    await fireEvent.click(screen.getByTestId("queue-load-more"));
    await waitFor(() => expect(queueIds()).toEqual(["a", "b", "c", "d"]));
    const asked = spotifyTrackUrls().at(-1);
    expect(asked).toContain("sort=recent");
    expect(asked).toContain("offset=2");

    // Near the end the player tops up on its own (Player.svelte runs this on every track change).
    currentTrack.set(get(playlist).at(-1));
    expect(await extendQueue()).toBe(true);
    expect(queueIds()).toEqual(["a", "b", "c", "d", "e"]);

    await waitFor(() => expect(screen.getByTestId("queue-load-more-end")).toBeTruthy());
    expect(screen.queryByTestId("queue-load-more")).toBeNull();
  });
});

describe("a filtered song list", () => {
  it("continues the queue with the filter it was started with", async () => {
    activeView.set("songs");
    render(Dashboard, { activeView: "songs" });
    await waitFor(() => expect(screen.getByText("Title a")).toBeTruthy());

    await fireEvent.change(screen.getByLabelText("Kwaliteit"), { target: { value: "lossless" } });
    await waitFor(() =>
      expect(spotifyTrackUrls().some((url) => url.includes("minQuality=lossless"))).toBe(true),
    );
    await waitFor(() => expect(screen.getAllByLabelText("Afspelen").length).toBe(2));
    await fireEvent.click(screen.getAllByLabelText("Afspelen")[1]);

    expect(get(currentTrack).id).toBe("b");
    // The last row is playing: that is near the end.
    expect(await extendQueue()).toBe(true);

    const asked = spotifyTrackUrls().at(-1);
    expect(asked).toContain("minQuality=lossless");
    expect(asked).toContain("offset=2");
    expect(queueIds()).toEqual(["a", "b", "c", "d"]);
  });

  it("a genre list hands its continuation to the queue as well", async () => {
    activeView.set("genre:Hardcore");
    render(Dashboard, { activeView: "genre:Hardcore" });
    await waitFor(() => expect(screen.getAllByLabelText("Afspelen").length).toBe(2));
    await fireEvent.click(screen.getAllByLabelText("Afspelen")[0]);

    await extendQueue({ force: true });

    expect(spotifyTrackUrls().at(-1)).toContain("genre=Hardcore");
    expect(queueIds()).toEqual(["a", "b", "c", "d"]);
  });
});

describe("a preset (dynamic playlist)", () => {
  const PRESET = normalizePreset({
    id: 21,
    name: "Random Hardcore",
    params: JSON.stringify({ genre: ["Hardcore"], sortMethod: "Random", length: "short", size: 2 }),
  });

  function songsUrls() {
    return globalThis.fetch.mock.calls
      .map(([url]) => String(url))
      .filter((url) => url.includes("/rest/getSongs?"));
  }

  it("goes on past its size on the page, with the same seed, and then ends", async () => {
    render(PresetView, { preset: PRESET, onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Title p2")).toBeTruthy());

    await fireEvent.click(screen.getByTestId("preset-load-more"));
    await waitFor(() => expect(screen.getByText("Title p3")).toBeTruthy());

    expect(screen.getByText("Einde van de lijst")).toBeTruthy();
    const [first, next] = songsUrls().map((url) => new URL(url, "http://x").searchParams);
    expect(next.get("offset")).toBe("2");
    expect(next.get("seed")).toBe(first.get("seed"));
  });

  it("its play button starts a queue that continues, shows the pill, and ends", async () => {
    render(PresetView, { preset: PRESET, onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Title p2")).toBeTruthy());

    await fireEvent.click(screen.getByLabelText("Alles afspelen"));
    expect(get(queueContinuation)).toMatchObject({ kind: "preset", cursor: 2 });

    render(QueueLoadMore);
    expect(screen.getByTestId("queue-load-more")).toBeTruthy();

    // Two tracks, the first playing: already within three of the end.
    expect(await extendQueue()).toBe(true);
    expect(queueIds()).toEqual(["p1", "p2", "p3"]);
    await waitFor(() => expect(screen.getByTestId("queue-load-more-end")).toBeTruthy());
  });
});
