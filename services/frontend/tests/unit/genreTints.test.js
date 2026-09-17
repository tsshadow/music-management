import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  fetchGenreTints,
  tintFor,
  withTints,
  trackTint,
  resetGenreTints,
} from "../../src/lib/genreTints.js";

/**
 * The colour a genre is drawn in comes from the server, not from a table in here.
 *
 * A table on each side would drift: Hardstyle orange in the web UI and magenta in the app is a
 * difference nobody notices until both are open next to each other, and nothing tests for it.
 */
describe("genreTints", () => {
  beforeEach(() => {
    resetGenreTints();
    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () =>
          Promise.resolve([
            { genre: "Hardstyle", count: 412, tint: "#ff4d00" },
            { genre: "Techno", count: 301, tint: "#00e0c7" },
          ]),
      }),
    );
  });

  afterEach(() => {
    resetGenreTints();
  });

  it("reads the colours the server sent", async () => {
    const tints = await fetchGenreTints();

    expect(tintFor(tints, "Hardstyle")).toBe("#ff4d00");
  });

  it("matches a genre whatever case it is written in", async () => {
    // The Subsonic list and MuMa's own list do not agree on capitalisation.
    const tints = await fetchGenreTints();

    expect(tintFor(tints, "HARDSTYLE")).toBe("#ff4d00");
    expect(tintFor(tints, " techno ")).toBe("#00e0c7");
  });

  it("has no colour for a genre the server did not mention", async () => {
    const tints = await fetchGenreTints();

    expect(tintFor(tints, "Frenchcore")).toBe(null);
  });

  it("asks the server once however many callers want the colours", async () => {
    await Promise.all([fetchGenreTints(), fetchGenreTints()]);
    await fetchGenreTints();

    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  it("returns no colours rather than failing when the server is unreachable", async () => {
    // The genre grid must still render. A card without its colour is a card; a page that threw
    // is not.
    global.fetch = vi.fn(() => Promise.reject(new Error("offline")));

    const tints = await fetchGenreTints();

    expect(tintFor(tints, "Hardstyle")).toBe(null);
  });

  it("puts the colour on the genres the grid already has", async () => {
    // The grid's names come from Subsonic's getGenres, which knows nothing about colour.
    const tints = await fetchGenreTints();

    const items = withTints([{ value: "Hardstyle" }, { value: "Techno" }], tints);

    expect(items[0].tint).toBe("#ff4d00");
    expect(items[1].tint).toBe("#00e0c7");
  });

  it("leaves a genre the server did not mention without a colour", async () => {
    const tints = await fetchGenreTints();

    const [item] = withTints([{ value: "Frenchcore", songCount: 12 }], tints);

    expect(item.tint).toBeUndefined();
    expect(item.songCount).toBe(12);
  });

  it("retries after a failure instead of caching the empty answer", async () => {
    global.fetch = vi.fn(() => Promise.reject(new Error("offline")));
    await fetchGenreTints();

    global.fetch = vi.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve([{ genre: "Hardstyle", tint: "#ff4d00" }]),
      }),
    );
    const tints = await fetchGenreTints();

    expect(tintFor(tints, "Hardstyle")).toBe("#ff4d00");
  });
});

describe("trackTint", () => {
  const TINTS = { hardstyle: "#ff4d00", techno: "#00e0c7" };

  it("picks the first genre with a tint", () => {
    expect(trackTint({ genre: "hardstyle,techno" }, TINTS)).toBe("#ff4d00");
  });

  it("skips a genre the server did not list and uses the next one", () => {
    expect(trackTint({ genre: "frenchcore,techno" }, TINTS)).toBe("#00e0c7");
  });

  it("returns null when no genre has a tint", () => {
    expect(trackTint({ genre: "frenchcore" }, TINTS)).toBe(null);
  });

  it("returns null for a track with no genres", () => {
    expect(trackTint({ genre: "" }, TINTS)).toBe(null);
    expect(trackTint(null, TINTS)).toBe(null);
    expect(trackTint(undefined, TINTS)).toBe(null);
  });
});
