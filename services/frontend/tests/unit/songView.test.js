import { beforeEach, describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/svelte";
import SongView from "../../src/lib/SongView.svelte";
import { entityCache, songVersionsKey } from "../../src/lib/entityLoaders.js";
import { clearSeeds, openSong } from "../../src/lib/entitySeeds.js";
import { pathToState, viewToPath } from "../../src/lib/router.js";

/**
 * One song and every file of it.
 *
 * The page exists because the lists collapse: the row you clicked is the version the
 * server chose, and the others never reached the browser. So everything here is fetched
 * by work id, and that is also what makes the alternatives playable — muma's own version
 * API answers with paths and muma ids, which the player cannot use.
 */

const version = (id, extra = {}) => ({
  id: String(id),
  title: "Raise Your Fist",
  artist: "Angerfist",
  artistId: "artist-1",
  duration: 200,
  ...extra,
});

const subsonic = (tracks) =>
  vi.fn(async () => ({
    ok: true,
    json: async () => ({ "subsonic-response": { status: "ok", tracks: { track: tracks } } }),
  }));

// Every test starts cold: the page answers a revisit from the entity cache, and the tests below
// all open work 42.
beforeEach(() => {
  entityCache.clear();
  clearSeeds();
});

describe("SongView", () => {
  it("asks the server for every version of the work", async () => {
    globalThis.fetch = subsonic([version(1, { isCanonical: true })]);

    render(SongView, { workId: "42", onnavigate: vi.fn() });

    await vi.waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(globalThis.fetch.mock.calls[0][0]).toContain("workId=42");
  });

  it("heads the page with the canonical, not with whatever came first", async () => {
    globalThis.fetch = subsonic([
      version(1, { title: "Raise Your Fist (Extended Mix)", isCanonical: false }),
      version(2, { title: "Raise Your Fist", isCanonical: true }),
    ]);

    render(SongView, { workId: "42", onnavigate: vi.fn() });

    await vi.waitFor(() =>
      expect(screen.getByRole("heading", { level: 2 }).textContent).toBe("Raise Your Fist"),
    );
  });

  it("lists every version", async () => {
    globalThis.fetch = subsonic([
      version(1, { isCanonical: true }),
      version(2, { title: "Raise Your Fist (Extended Mix)", isCanonical: false }),
    ]);

    render(SongView, { workId: "42", onnavigate: vi.fn() });

    await vi.waitFor(() => expect(screen.getByText("2 versies")).toBeTruthy());
    expect(screen.getByText("Raise Your Fist (Extended Mix)")).toBeTruthy();
  });

  it("says so when the song has only one version", async () => {
    globalThis.fetch = subsonic([version(1, { isCanonical: true })]);

    render(SongView, { workId: "42", onnavigate: vi.fn() });

    await vi.waitFor(() =>
      expect(screen.getByText("Dit is de enige versie van dit nummer.")).toBeTruthy(),
    );
  });

  it("says what went wrong instead of showing an empty page", async () => {
    // Subsonic reports its failures with HTTP 200 and an error in the body, so a page
    // that only checked the status code would sit there empty and blame nothing.
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": { status: "failed", error: { message: "no such work" } },
      }),
    }));

    render(SongView, { workId: "42", onnavigate: vi.fn() });

    await vi.waitFor(() =>
      expect(screen.getByText("De versies van dit nummer konden niet worden geladen")).toBeTruthy(),
    );
  });
});

describe("SongView paging and staleness", () => {
  it("follows the server's pages instead of stopping at the first", async () => {
    // A version list that is silently cut short is invisible afterwards: the page looks
    // complete and simply misses files.
    const page = (tracks, more, nextOffset) =>
      Promise.resolve({
        ok: true,
        json: async () => ({
          "subsonic-response": {
            status: "ok",
            tracks: { track: tracks, moreResults: more, nextOffset },
          },
        }),
      });
    globalThis.fetch = vi
      .fn()
      .mockImplementationOnce(() => page([version(1, { isCanonical: true })], true, 100))
      .mockImplementationOnce(() => page([version(2, { title: "Second page" })], false));

    render(SongView, { workId: "42", onnavigate: vi.fn() });

    await vi.waitFor(() => expect(screen.getByText("Second page")).toBeTruthy());
    expect(globalThis.fetch.mock.calls[1][0]).toContain("offset=100");
  });

  it("stops paging when the server says there is no more", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": {
          status: "ok",
          tracks: { track: [version(1, { isCanonical: true })], moreResults: false },
        },
      }),
    }));

    render(SongView, { workId: "42", onnavigate: vi.fn() });

    await vi.waitFor(() => expect(screen.getByRole("heading", { level: 2 })).toBeTruthy());
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });
});

describe("the song route", () => {
  it("survives the trip to a path and back", () => {
    expect(viewToPath({ view: "song:42" })).toBe("/song/42");
    expect(pathToState("/song/42").view).toBe("song:42");
  });
});

/**
 * Issue #111: the page opens at once from the row that was tapped, and the versions stream in page
 * by page instead of behind a whole-page "Laden...".
 */
describe("SongView optimistic shell", () => {
  const okPage = (tracks, more, nextOffset) => ({
    ok: true,
    json: async () => ({
      "subsonic-response": {
        status: "ok",
        tracks: { track: tracks, moreResults: more, nextOffset },
      },
    }),
  });

  it("heads the page with the tapped row's title, artist and cover before the server answers", () => {
    globalThis.fetch = vi.fn(() => new Promise(() => {}));
    const navigate = vi.fn();
    openSong(navigate, {
      workId: "42",
      title: "Raise Your Fist",
      artist: "Angerfist",
      artistId: "artist-1",
      coverArt: "al-1",
    });
    expect(navigate).toHaveBeenCalledWith("song:42");

    render(SongView, { workId: "42", onnavigate: vi.fn() });

    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe("Raise Your Fist");
    expect(screen.getByText("Angerfist")).toBeTruthy();
    expect(screen.getByTestId("song-cover").getAttribute("src")).toContain("al-1");
    expect(screen.getByTestId("skeleton-rows")).toBeTruthy();
    expect(screen.queryByText("Laden...")).toBeNull();
  });

  it("draws a skeleton header when opened by URL with nothing known", () => {
    globalThis.fetch = vi.fn(() => new Promise(() => {}));

    render(SongView, { workId: "42", onnavigate: vi.fn() });

    expect(screen.getByTestId("song-title-skeleton")).toBeTruthy();
    expect(screen.getByTestId("skeleton-rows")).toBeTruthy();
  });

  it("shows the first page while the next one is still on its way", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        okPage([version(1, { isCanonical: true, title: "First page" })], true, 100),
      )
      .mockImplementationOnce(() => new Promise(() => {}));

    render(SongView, { workId: "42", onnavigate: vi.fn() });

    await vi.waitFor(() => expect(screen.getAllByText("First page").length).toBeGreaterThan(0));
    expect(screen.getByTestId("skeleton-rows")).toBeTruthy();
    expect(screen.getByTestId("throbber")).toBeTruthy();
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it("keeps the seed in the header until the canonical is seen, not the first version", async () => {
    globalThis.fetch = vi
      .fn()
      .mockResolvedValueOnce(
        okPage([version(1, { title: "Raise Your Fist (Extended Mix)" })], true, 100),
      )
      .mockImplementationOnce(() => new Promise(() => {}));
    openSong(vi.fn(), { workId: "42", title: "Raise Your Fist", artist: "Angerfist" });

    render(SongView, { workId: "42", onnavigate: vi.fn() });

    await vi.waitFor(() => expect(screen.getByText("Raise Your Fist (Extended Mix)")).toBeTruthy());
    expect(screen.getByRole("heading", { level: 2 }).textContent).toBe("Raise Your Fist");
  });

  it("offers a retry when the versions could not be loaded, and loads them on retry", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ "subsonic-response": { status: "failed", error: { message: "x" } } }),
    }));
    render(SongView, { workId: "42", onnavigate: vi.fn() });
    await vi.waitFor(() => expect(screen.getByTestId("section-error")).toBeTruthy());

    globalThis.fetch = vi.fn(async () => okPage([version(1, { isCanonical: true })], false));
    await fireEvent.click(screen.getByText("Opnieuw"));

    await vi.waitFor(() =>
      expect(screen.getByText("Dit is de enige versie van dit nummer.")).toBeTruthy(),
    );
    expect(screen.queryByTestId("section-error")).toBeNull();
  });

  it("answers a revisit from the cache without asking the server", () => {
    globalThis.fetch = vi.fn(() => new Promise(() => {}));
    entityCache.set(songVersionsKey("42"), [
      version(1, { isCanonical: true }),
      version(2, { title: "Raise Your Fist (Extended Mix)" }),
    ]);

    render(SongView, { workId: "42", onnavigate: vi.fn() });

    expect(screen.getByText("2 versies")).toBeTruthy();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
