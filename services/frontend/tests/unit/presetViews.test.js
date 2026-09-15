/**
 * The preset tiles on Home and the page behind one.
 *
 * The grid is a list of buttons; what matters is that a tap hands the preset back and never
 * starts playback itself. The page fetches through `getSongs` with the tile's clusters, shows
 * the pages as they arrive, and its play button loads that list into the player in order.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

import PresetGrid from "../../src/lib/PresetGrid.svelte";
import PresetView from "../../src/lib/PresetView.svelte";
import { normalizePreset, presets } from "../../src/lib/presets.js";
import {
  credentials,
  currentTrack,
  mumaApiKey,
  mumaUser,
  playerState,
  playlist,
  viewMode,
} from "../../src/lib/store.js";

const RANDOM_UPTEMPO = normalizePreset({
  id: 15,
  name: "Random Uptempo",
  params: JSON.stringify({
    genre: ["Uptempo Hardcore"],
    sortMethod: "Random",
    length: "short",
    size: 150,
  }),
});

const RECENT = normalizePreset({
  id: 16,
  name: "Recent",
  params: JSON.stringify({ sortMethod: "AddedDesc", size: 100 }),
});

const SONGS = [
  { id: "song-1", title: "Raise Your Fist", artist: "Angerfist", suffix: "flac" },
  { id: "song-2", title: "Second", artist: "Someone", suffix: "mp3" },
];

/** Answers every `/rest/getSongs` page with `pages.shift()`, and anything else with `{}`. */
function lms(pages) {
  return vi.fn(async (url) => {
    const isSongs = String(url).includes("/rest/getSongs?");
    const song = isSongs ? (pages.shift() ?? []) : [];
    return {
      ok: true,
      json: async () => (isSongs ? { "subsonic-response": { songs: { song } } } : {}),
    };
  });
}

describe("PresetGrid", () => {
  it("draws one tile per preset with its name and its summary", () => {
    render(PresetGrid, { presets: [RANDOM_UPTEMPO, RECENT], onopen: vi.fn() });

    expect(screen.getByText("Random Uptempo")).toBeTruthy();
    expect(screen.getByText("Willekeurig · Uptempo Hardcore")).toBeTruthy();
    expect(screen.getByText("Recent toegevoegd · alles")).toBeTruthy();
  });

  it("hands the preset back on a tap", async () => {
    const onopen = vi.fn();
    render(PresetGrid, { presets: [RANDOM_UPTEMPO], onopen });

    await fireEvent.click(screen.getByText("Random Uptempo"));

    expect(onopen).toHaveBeenCalledWith(RANDOM_UPTEMPO);
  });

  it("is not there at all without presets", () => {
    render(PresetGrid, { presets: [], onopen: vi.fn() });
    expect(screen.queryByTestId("preset-grid")).toBeNull();
  });
});

describe("PresetView", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    viewMode.set("songs");
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    mumaUser.set({ id: 7, username: "user" });
    mumaApiKey.set("key");
    presets.set([RANDOM_UPTEMPO, RECENT]);
    globalThis.fetch = lms([SONGS]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("asks LMS for the tile's clusters and lists what came back", async () => {
    render(PresetView, { preset: RANDOM_UPTEMPO, onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());

    // The store also syncs account settings on a user change; only the LMS call is of interest.
    const call = globalThis.fetch.mock.calls.find(([url]) =>
      String(url).includes("/rest/getSongs?"),
    );
    const url = decodeURIComponent(String(call[0]));
    expect(url).toContain('{"name":"GENRE","value":["Uptempo Hardcore"]}');
    expect(url).toContain('{"name":"LENGTH","value":"short"}');
    expect(url).toContain("sortMethod=Random");
  });

  it("keeps paging until the preset's size or a short page", async () => {
    const full = Array.from({ length: 100 }, (_, i) => ({
      id: `s${i}`,
      title: `T${i}`,
      artist: "a",
    }));
    globalThis.fetch = lms([full, SONGS]);

    render(PresetView, { preset: RANDOM_UPTEMPO, onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText(/102 nummers/)).toBeTruthy());
    const songsCalls = globalThis.fetch.mock.calls.filter(([url]) =>
      String(url).includes("/rest/getSongs?"),
    );
    // 150 wanted: a full first page, then a page of 50 that came back short, so no third.
    expect(songsCalls).toHaveLength(2);
    expect(String(songsCalls[1][0])).toContain("offset=100");
    expect(String(songsCalls[1][0])).toContain("count=50");
  });

  it("queues the list in order and starts it", async () => {
    render(PresetView, { preset: RANDOM_UPTEMPO, onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());

    await fireEvent.click(screen.getByTitle("Alles afspelen"));

    expect(get(playlist).map((track) => track.id)).toEqual(["song-1", "song-2"]);
    expect(get(currentTrack).id).toBe("song-1");
    expect(get(playerState).playing).toBe(true);
  });

  it("says so when the query matches nothing", async () => {
    globalThis.fetch = lms([[]]);

    render(PresetView, { preset: RECENT, onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Geen nummers voor deze preset.")).toBeTruthy());
    expect(screen.queryByTitle("Alles afspelen")).toBeNull();
  });

  it("deletes the preset from MuMa after a confirmation and goes home", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const onnavigate = vi.fn();
    globalThis.fetch = vi.fn(async (url) => {
      if (String(url).includes("/rest/getSongs?")) {
        return {
          ok: true,
          json: async () => ({ "subsonic-response": { songs: { song: SONGS } } }),
        };
      }
      return { ok: true, json: async () => [] };
    });

    render(PresetView, { preset: RANDOM_UPTEMPO, onnavigate });
    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());

    await fireEvent.click(screen.getByLabelText("Meer"));
    await fireEvent.click(screen.getByRole("menuitem", { name: "Preset verwijderen" }));

    await waitFor(() => expect(onnavigate).toHaveBeenCalledWith("home"));
    const remove = globalThis.fetch.mock.calls.find(([, options]) => options?.method === "DELETE");
    expect(String(remove[0])).toContain("/api/users/7/dynamic-playlists/15");
    expect(get(presets)).toEqual([]);
  });

  it("leaves the preset alone when the confirmation is refused", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);

    render(PresetView, { preset: RANDOM_UPTEMPO, onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());

    await fireEvent.click(screen.getByLabelText("Meer"));
    await fireEvent.click(screen.getByRole("menuitem", { name: "Preset verwijderen" }));

    expect(globalThis.fetch.mock.calls.some(([, options]) => options?.method === "DELETE")).toBe(
      false,
    );
  });
});
