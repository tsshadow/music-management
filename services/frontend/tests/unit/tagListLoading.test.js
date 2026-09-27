/**
 * Loading states of the tag track lists and the search results page (issues #109 and #112,
 * docs/designs/perceived-performance/): a new place never shows the previous place's rows,
 * skeletons stand in until the answer, a failure is a section error with a retry, a revisit comes
 * from the cache, and a press on a card starts the list's request.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/svelte";

import Dashboard from "../../src/lib/Dashboard.svelte";
import { resetFeedsCache } from "../../src/lib/feeds.js";
import { trackListCache } from "../../src/lib/trackListCache.js";
import {
  credentials,
  deduplicateEnabled,
  favoriteGenres,
  memoriesOnHomeEnabled,
  subsonicToken,
  viewMode,
} from "../../src/lib/store.js";

const track = (id, title) => ({
  id,
  title,
  artist: "Track Artist",
  artistId: "ar-9",
  duration: 200,
});

const ok = (payload) => ({
  ok: true,
  json: async () => ({ "subsonic-response": { status: "ok", ...payload } }),
});

/**
 * A fetch whose list answers the test hands out: every track, artist and album list request
 * waits in `pending` until `answer` resolves it (or `fail` rejects it). Everything else is
 * answered at once, with a genre list for the genres page.
 */
function heldFetch() {
  const pending = [];
  const fetch = vi.fn((url) => {
    const held = ["getSpotifyTracks", "getArtistList", "getAlbumList2"].some((m) =>
      url.includes(m),
    );
    if (!held) {
      return Promise.resolve(
        ok({
          genres: {
            genre: [
              { value: "Hardcore", songCount: 1200 },
              { value: "Uptempo", songCount: 900 },
            ],
          },
        }),
      );
    }
    return new Promise((resolve, reject) => pending.push({ url, resolve, reject }));
  });
  /** Resolves the first held request whose URL contains every fragment. */
  const find = (fragments) => {
    const index = pending.findIndex((entry) => fragments.every((f) => entry.url.includes(f)));
    if (index < 0) throw new Error(`no held request for ${fragments.join(", ")}`);
    return pending.splice(index, 1)[0];
  };
  return {
    fetch,
    pending,
    count: (fragment) => fetch.mock.calls.filter(([url]) => url.includes(fragment)).length,
    answerTracks(fragments, tracks) {
      find(fragments).resolve(ok({ tracks: { track: tracks, moreResults: false } }));
    },
    answer(fragments, payload) {
      find(fragments).resolve(ok(payload));
    },
    fail(fragments) {
      find(fragments).reject(new Error("network down"));
    },
  };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("tag track lists (issue #109)", () => {
  let server;

  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    subsonicToken.set({ username: "user", token: "test-subsonic-token" });
    viewMode.set("songs");
    deduplicateEnabled.set(false);
    favoriteGenres.set([]);
    memoriesOnHomeEnabled.set(false);
    resetFeedsCache();
    trackListCache.clear();
    server = heldFetch();
    globalThis.fetch = server.fetch;
  });

  afterEach(() => vi.restoreAllMocks());

  it("shows skeleton rows under the genre's name before the first answer", async () => {
    render(Dashboard, { activeView: "genre:Hardcore" });

    expect(await screen.findByTestId("skeleton-rows")).toBeTruthy();
    expect(screen.getByText("Hardcore")).toBeTruthy();
    expect(screen.queryByText("Geen nummers gevonden")).toBeNull();

    await waitFor(() => expect(server.count("genre=Hardcore")).toBe(1));
    server.answerTracks(["genre=Hardcore"], [track("h1", "Hard One")]);
    expect(await screen.findByText("Hard One")).toBeTruthy();
    expect(screen.queryByTestId("skeleton-rows")).toBeNull();
  });

  it("never shows the previous genre's rows under the next genre's name", async () => {
    const { rerender } = render(Dashboard, { activeView: "genre:Hardcore" });
    await waitFor(() => expect(server.count("genre=Hardcore")).toBe(1));
    server.answerTracks(["genre=Hardcore"], [track("h1", "Hard One")]);
    expect(await screen.findByText("Hard One")).toBeTruthy();

    await rerender({ activeView: "genre:Uptempo" });

    expect(screen.getByText("Uptempo")).toBeTruthy();
    expect(screen.queryByText("Hard One")).toBeNull();
    expect(screen.getByTestId("skeleton-rows")).toBeTruthy();

    await waitFor(() => expect(server.count("genre=Uptempo")).toBe(1));
    server.answerTracks(["genre=Uptempo"], [track("u1", "Fast One")]);
    expect(await screen.findByText("Fast One")).toBeTruthy();
  });

  it("clears the rows when moving between kinds as well (label to festival)", async () => {
    const { rerender } = render(Dashboard, { activeView: "label:Roughstate" });
    await waitFor(() => expect(server.count("label=Roughstate")).toBe(1));
    server.answerTracks(["label=Roughstate"], [track("l1", "Label Track")]);
    expect(await screen.findByText("Label Track")).toBeTruthy();

    await rerender({ activeView: "festival:Defqon.1 2025" });

    expect(screen.queryByText("Label Track")).toBeNull();
    expect(screen.getByTestId("skeleton-rows")).toBeTruthy();
  });

  it("drops a late answer for a genre the listener already left", async () => {
    const { rerender } = render(Dashboard, { activeView: "genre:Hardcore" });
    await waitFor(() => expect(server.count("genre=Hardcore")).toBe(1));

    await rerender({ activeView: "genre:Uptempo" });
    await waitFor(() => expect(server.count("genre=Uptempo")).toBe(1));
    server.answerTracks(["genre=Uptempo"], [track("u1", "Fast One")]);
    expect(await screen.findByText("Fast One")).toBeTruthy();

    // The first request was aborted; even if its answer arrived it must not replace the list.
    server.pending
      .filter((entry) => entry.url.includes("genre=Hardcore"))
      .forEach((entry) =>
        entry.resolve(ok({ tracks: { track: [track("h1", "Hard One")], moreResults: false } })),
      );
    await flush();
    expect(screen.queryByText("Hard One")).toBeNull();
    expect(screen.getByText("Fast One")).toBeTruthy();
  });

  it("shows the section error with a retry when the list fails, and the retry loads it", async () => {
    render(Dashboard, { activeView: "genre:Hardcore" });
    await waitFor(() => expect(server.count("genre=Hardcore")).toBe(1));

    server.fail(["genre=Hardcore"]);

    const error = await screen.findByTestId("section-error");
    expect(screen.queryByText("Geen nummers gevonden")).toBeNull();
    await fireEvent.click(within(error).getByRole("button", { name: "Opnieuw" }));

    expect(await screen.findByTestId("skeleton-rows")).toBeTruthy();
    await waitFor(() => expect(server.count("genre=Hardcore")).toBe(2));
    server.answerTracks(["genre=Hardcore"], [track("h1", "Hard One")]);
    expect(await screen.findByText("Hard One")).toBeTruthy();
  });

  it("shows a genre seen a moment ago at once from the cache, without asking again", async () => {
    const { rerender } = render(Dashboard, { activeView: "genre:Hardcore" });
    await waitFor(() => expect(server.count("genre=Hardcore")).toBe(1));
    server.answerTracks(["genre=Hardcore"], [track("h1", "Hard One")]);
    expect(await screen.findByText("Hard One")).toBeTruthy();

    await rerender({ activeView: "genre:Uptempo" });
    await rerender({ activeView: "genre:Hardcore" });

    expect(screen.getByText("Hard One")).toBeTruthy();
    expect(screen.queryByTestId("skeleton-rows")).toBeNull();
    await flush();
    expect(server.count("genre=Hardcore")).toBe(1);
  });

  it("refreshes a cached list in the background once it is no longer fresh", async () => {
    const now = vi.spyOn(Date, "now");
    const start = 1_000_000;
    now.mockReturnValue(start);
    const { rerender } = render(Dashboard, { activeView: "genre:Hardcore" });
    await waitFor(() => expect(server.count("genre=Hardcore")).toBe(1));
    server.answerTracks(["genre=Hardcore"], [track("h1", "Hard One")]);
    expect(await screen.findByText("Hard One")).toBeTruthy();

    await rerender({ activeView: "genre:Uptempo" });
    now.mockReturnValue(start + 2 * 60_000);
    await rerender({ activeView: "genre:Hardcore" });

    // The old copy stays on screen while the new one is on its way.
    expect(screen.getByText("Hard One")).toBeTruthy();
    await waitFor(() => expect(server.count("genre=Hardcore")).toBe(2));
    server.answerTracks(["genre=Hardcore"], [track("h2", "Hard Two")]);
    expect(await screen.findByText("Hard Two")).toBeTruthy();
    expect(screen.queryByText("Hard One")).toBeNull();
  });

  it("starts the list's request when a genre card is pressed, and the page reuses it", async () => {
    const { rerender } = render(Dashboard, { activeView: "genres" });
    const card = await screen.findByRole("button", { name: /Uptempo/ });

    await fireEvent.pointerDown(card);
    expect(server.count("genre=Uptempo")).toBe(1);

    await rerender({ activeView: "genre:Uptempo" });
    await flush();
    // One request for the press and the page together.
    expect(server.count("genre=Uptempo")).toBe(1);
    server.answerTracks(["genre=Uptempo"], [track("u1", "Fast One")]);
    expect(await screen.findByText("Fast One")).toBeTruthy();
  });

  it("does not prefetch when the favourite toggle on a card is pressed", async () => {
    render(Dashboard, { activeView: "genres" });
    await screen.findByRole("button", { name: /Uptempo/ });

    const toggles = screen.getAllByLabelText("Favoriet toggelen");
    await fireEvent.pointerDown(toggles[0]);

    expect(server.count("getSpotifyTracks")).toBe(0);
  });

  it("dims the rows of the same list while a filter change is answered", async () => {
    render(Dashboard, { activeView: "genre:Hardcore" });
    await waitFor(() => expect(server.count("genre=Hardcore")).toBe(1));
    server.answerTracks(["genre=Hardcore"], [track("h1", "Hard One")]);
    expect(await screen.findByText("Hard One")).toBeTruthy();

    // Same place, new question: the old rows stay, dimmed, instead of a skeleton flash.
    await fireEvent.change(screen.getByLabelText("Kwaliteit"), { target: { value: "lossless" } });

    await waitFor(() => expect(server.count("minQuality=lossless")).toBe(1));
    expect(screen.getByTestId("track-list-rows").dataset.stale).toBe("true");
    expect(screen.getByText("Hard One")).toBeTruthy();
    expect(screen.queryByTestId("skeleton-rows")).toBeNull();

    server.answerTracks(["minQuality=lossless"], [track("h9", "Lossless One")]);
    expect(await screen.findByText("Lossless One")).toBeTruthy();
    expect(screen.getByTestId("track-list-rows").dataset.stale).toBeUndefined();
  });
});

describe("search results page (issue #112)", () => {
  let server;

  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    subsonicToken.set({ username: "user", token: "test-subsonic-token" });
    viewMode.set("songs");
    deduplicateEnabled.set(false);
    resetFeedsCache();
    trackListCache.clear();
    server = heldFetch();
    globalThis.fetch = server.fetch;
  });

  afterEach(() => vi.restoreAllMocks());

  it("shows a skeleton per section and says it is searching, never 'No results' before the answer", async () => {
    render(Dashboard, { activeView: "search:anger" });

    expect(await screen.findByTestId("skeleton-rows")).toBeTruthy();
    expect(screen.getAllByTestId("skeleton-tiles")).toHaveLength(2);
    expect(screen.getByTestId("search-pending")).toBeTruthy();
    expect(screen.queryByText("Geen resultaten gevonden.")).toBeNull();

    await waitFor(() => expect(server.pending).toHaveLength(3));
    server.answerTracks(["getSpotifyTracks"], []);
    server.answer(["getArtistList"], { artistList: { artist: [] } });
    await flush();
    // One section still out: still no verdict.
    expect(screen.queryByText("Geen resultaten gevonden.")).toBeNull();
    server.answer(["getAlbumList2"], { albumList2: { album: [] } });

    expect(await screen.findByText("Geen resultaten gevonden.")).toBeTruthy();
    expect(screen.queryByTestId("search-pending")).toBeNull();
  });

  it("fills each section as its own answer arrives", async () => {
    render(Dashboard, { activeView: "search:anger" });
    await waitFor(() => expect(server.pending).toHaveLength(3));

    server.answer(["getArtistList"], {
      artistList: { artist: [{ id: "ar-1", name: "Angerfist" }] },
    });

    expect(await screen.findByText("Angerfist")).toBeTruthy();
    // Tracks and albums are still skeletons.
    expect(screen.getByTestId("skeleton-rows")).toBeTruthy();
    expect(screen.getAllByTestId("skeleton-tiles")).toHaveLength(1);
  });

  it("does not show the previous search's results under the new query", async () => {
    const { rerender } = render(Dashboard, { activeView: "search:anger" });
    await waitFor(() => expect(server.pending).toHaveLength(3));
    server.answerTracks(["getSpotifyTracks"], [track("t1", "Raise Your Fist")]);
    server.answer(["getArtistList"], {
      artistList: { artist: [{ id: "ar-1", name: "Angerfist" }] },
    });
    server.answer(["getAlbumList2"], { albumList2: { album: [] } });
    expect(await screen.findByText("Raise Your Fist")).toBeTruthy();

    await rerender({ activeView: "search:dither" });

    expect(screen.queryByText("Raise Your Fist")).toBeNull();
    expect(screen.queryByText("Angerfist")).toBeNull();
    expect(screen.getByTestId("skeleton-rows")).toBeTruthy();
  });

  it("gives a failing section its own error and retry, leaving the others", async () => {
    render(Dashboard, { activeView: "search:anger" });
    await waitFor(() => expect(server.pending).toHaveLength(3));
    server.answerTracks(["getSpotifyTracks"], [track("t1", "Raise Your Fist")]);
    server.fail(["getArtistList"]);
    server.answer(["getAlbumList2"], { albumList2: { album: [] } });

    const error = await screen.findByTestId("section-error");
    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
    expect(screen.queryByText("Geen resultaten gevonden.")).toBeNull();

    await fireEvent.click(within(error).getByRole("button", { name: "Opnieuw" }));
    await waitFor(() => expect(server.count("getArtistList")).toBe(2));
    server.answer(["getArtistList"], {
      artistList: { artist: [{ id: "ar-1", name: "Angerfist" }] },
    });
    expect(await screen.findByText("Angerfist")).toBeTruthy();
  });

  it("shows a search run a moment ago at once from the cache", async () => {
    const { rerender } = render(Dashboard, { activeView: "search:anger" });
    await waitFor(() => expect(server.pending).toHaveLength(3));
    server.answerTracks(["getSpotifyTracks"], [track("t1", "Raise Your Fist")]);
    server.answer(["getArtistList"], {
      artistList: { artist: [{ id: "ar-1", name: "Angerfist" }] },
    });
    server.answer(["getAlbumList2"], { albumList2: { album: [] } });
    expect(await screen.findByText("Angerfist")).toBeTruthy();

    await rerender({ activeView: "search:dither" });
    await rerender({ activeView: "search:anger" });

    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
    expect(screen.getByText("Angerfist")).toBeTruthy();
    expect(screen.queryByTestId("skeleton-rows")).toBeNull();
  });
});
