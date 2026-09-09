import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/svelte";
import SongView from "../../src/lib/SongView.svelte";
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

describe("the song route", () => {
  it("survives the trip to a path and back", () => {
    expect(viewToPath({ view: "song:42" })).toBe("/song/42");
    expect(pathToState("/song/42").view).toBe("song:42");
  });
});
