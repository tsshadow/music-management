/**
 * Skeleton sections instead of whole-body loaders (issue #112, docs/designs/perceived-performance/):
 * History, Starred, Memories and the search "more" modal draw their header at once, skeletons
 * where the content goes, and an error with a retry rather than an empty-state claim when the
 * request fails.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";

import History from "../../src/lib/History.svelte";
import StarredView from "../../src/lib/StarredView.svelte";
import MemoriesView from "../../src/lib/MemoriesView.svelte";
import MemoriesYearView from "../../src/lib/MemoriesYearView.svelte";
import SearchMoreModal from "../../src/lib/SearchMoreModal.svelte";
import { credentials, deduplicateEnabled, subsonicToken, viewMode } from "../../src/lib/store.js";

const SONG = { id: "s1", title: "Raise Your Fist", artist: "Angerfist", duration: 200 };

/** A fetch that holds every request until `release` answers it with `payload`. */
function holdAll() {
  const held = [];
  globalThis.fetch = vi.fn(() => new Promise((resolve, reject) => held.push({ resolve, reject })));
  return {
    count: () => globalThis.fetch.mock.calls.length,
    release(payload) {
      held.shift().resolve({
        ok: true,
        json: async () => ({ "subsonic-response": { status: "ok", ...payload } }),
      });
    },
    fail() {
      held.shift().reject(new Error("network down"));
    },
  };
}

beforeEach(() => {
  credentials.set({ url: "", username: "demo-user", password: "pw" });
  subsonicToken.set({ username: "demo-user", token: "test-subsonic-token" });
  viewMode.set("songs");
  deduplicateEnabled.set(false);
});

afterEach(() => vi.restoreAllMocks());

describe("History", () => {
  it("shows its heading and skeleton rows before the first page, never the empty line", async () => {
    const server = holdAll();
    render(History, { onnavigate: vi.fn() });

    expect(screen.getByText("Luistergeschiedenis")).toBeTruthy();
    expect(await screen.findByTestId("skeleton-rows")).toBeTruthy();
    expect(screen.queryByText("Nog geen luistergeschiedenis gevonden.")).toBeNull();

    server.release({ history: { entry: [SONG], moreResults: false } });
    expect(await screen.findByText("Raise Your Fist")).toBeTruthy();
    expect(screen.queryByTestId("skeleton-rows")).toBeNull();
  });

  it("offers a retry when the first page fails, and the retry loads it", async () => {
    const server = holdAll();
    render(History, { onnavigate: vi.fn() });
    await waitFor(() => expect(server.count()).toBe(1));

    server.fail();

    await fireEvent.click(await screen.findByRole("button", { name: "Opnieuw" }));
    expect(await screen.findByTestId("skeleton-rows")).toBeTruthy();
    await waitFor(() => expect(server.count()).toBe(2));
    server.release({ history: { entry: [SONG], moreResults: false } });
    expect(await screen.findByText("Raise Your Fist")).toBeTruthy();
  });

  it("keeps the rows on screen while the refresh button reloads them", async () => {
    const server = holdAll();
    render(History, { onnavigate: vi.fn() });
    await waitFor(() => expect(server.count()).toBe(1));
    server.release({ history: { entry: [SONG], moreResults: false } });
    expect(await screen.findByText("Raise Your Fist")).toBeTruthy();

    await fireEvent.click(screen.getByRole("button", { name: /Vernieuwen/ }));

    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
    expect(screen.queryByTestId("skeleton-rows")).toBeNull();
    expect(screen.getByTestId("throbber")).toBeTruthy();
  });
});

describe("StarredView", () => {
  it("draws its header at once and skeleton rows where the songs go", async () => {
    const server = holdAll();
    render(StarredView, { onnavigate: vi.fn() });

    expect(screen.getByRole("heading", { level: 1 })).toBeTruthy();
    expect(await screen.findByTestId("skeleton-rows")).toBeTruthy();
    expect(screen.queryByText("Nog geen favorieten")).toBeNull();

    server.release({ starred2: { song: [SONG] } });
    expect(await screen.findByText("Raise Your Fist")).toBeTruthy();
    expect(screen.queryByTestId("skeleton-rows")).toBeNull();
  });

  it("retries a failed load from the error line", async () => {
    const server = holdAll();
    render(StarredView, { onnavigate: vi.fn() });
    await waitFor(() => expect(server.count()).toBe(1));
    server.fail();

    await fireEvent.click(await screen.findByRole("button", { name: "Opnieuw" }));
    await waitFor(() => expect(server.count()).toBe(2));
    server.release({ starred2: { song: [SONG] } });
    expect(await screen.findByText("Raise Your Fist")).toBeTruthy();
  });
});

describe("Memories", () => {
  it("shows skeleton year tiles under the heading while loading", async () => {
    holdAll();
    render(MemoriesView, { onnavigate: vi.fn() });

    expect(screen.getByRole("heading", { level: 1 })).toBeTruthy();
    expect(await screen.findByTestId("skeleton-tiles")).toBeTruthy();
    expect(screen.queryByText("Laden…")).toBeNull();
  });

  it("shows the year at once and skeleton rows for its tracks", async () => {
    holdAll();
    render(MemoriesYearView, { year: "2019", onnavigate: vi.fn() });

    expect(screen.getByRole("heading", { level: 1, name: "2019" })).toBeTruthy();
    expect(await screen.findByTestId("skeleton-rows")).toBeTruthy();
  });
});

describe("SearchMoreModal", () => {
  it("shows skeleton rows for tracks and skeleton tiles for artists, not a spinner", async () => {
    holdAll();
    const { unmount } = render(SearchMoreModal, { query: "anger", category: "tracks" });
    expect(await screen.findByTestId("skeleton-rows")).toBeTruthy();
    unmount();

    holdAll();
    render(SearchMoreModal, { query: "anger", category: "artists" });
    expect(await screen.findByTestId("skeleton-tiles")).toBeTruthy();
  });

  it("offers a retry instead of 'No results' when the search fails", async () => {
    const server = holdAll();
    render(SearchMoreModal, { query: "anger", category: "tracks" });
    await waitFor(() => expect(server.count()).toBe(1));

    server.fail();

    await fireEvent.click(await screen.findByRole("button", { name: "Opnieuw" }));
    expect(screen.queryByText("Geen resultaten gevonden.")).toBeNull();
    await waitFor(() => expect(server.count()).toBe(2));
    server.release({ searchResult3: { song: [SONG] } });
    expect(await screen.findByText("Raise Your Fist")).toBeTruthy();
  });
});
