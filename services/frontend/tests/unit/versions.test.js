import { describe, it, expect, vi } from "vitest";
import { loadVersions } from "../../src/lib/versions.js";

/**
 * The paging loop `SongView.svelte`'s full page and `NowPlaying.svelte`'s "other versions"
 * section both rely on. Everything here used to live only in `SongView.svelte`; these tests
 * moved with the loop rather than being written fresh, so they still describe the same two
 * hazards a work id's version list has always had -- a silently truncated page, and Subsonic's
 * habit of reporting its own failures with HTTP 200.
 */

const version = (id, extra = {}) => ({
  id: String(id),
  title: "Raise Your Fist",
  artist: "Angerfist",
  duration: 200,
  ...extra,
});

const subsonic = (tracks, extra = {}) =>
  (globalThis.fetch = vi.fn(async () => ({
    ok: true,
    json: async () => ({
      "subsonic-response": { status: "ok", tracks: { track: tracks, ...extra } },
    }),
  })));

describe("loadVersions", () => {
  it("follows the server's pages instead of stopping at the first", async () => {
    globalThis.fetch = vi
      .fn()
      .mockImplementationOnce(async () => ({
        ok: true,
        json: async () => ({
          "subsonic-response": {
            status: "ok",
            tracks: { track: [version(1)], moreResults: true, nextOffset: 100 },
          },
        }),
      }))
      .mockImplementationOnce(async () => ({
        ok: true,
        json: async () => ({
          "subsonic-response": { status: "ok", tracks: { track: [version(2)] } },
        }),
      }));

    const versions = await loadVersions("42");

    expect(versions.map((v) => v.id)).toEqual(["1", "2"]);
    expect(globalThis.fetch.mock.calls[1][0]).toContain("offset=100");
  });

  it("stops paging when the server reports no more, even under max", async () => {
    subsonic([version(1)], { moreResults: false });

    const versions = await loadVersions("42", { max: 500 });

    expect(versions).toHaveLength(1);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });

  // The player's "other versions" section only ever wants a handful -- `max` bounds the total
  // this returns and the size of the request it makes, so a work with a long tail does not pay
  // for versions nobody will see.
  it("stops at max rather than fetching everything", async () => {
    subsonic(
      Array.from({ length: 6 }, (_, i) => version(i + 1)),
      { moreResults: true, nextOffset: 6 },
    );

    const versions = await loadVersions("42", { max: 6 });

    expect(versions).toHaveLength(6);
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
    expect(globalThis.fetch.mock.calls[0][0]).toContain("count=6");
  });

  it("throws when the server reports a failure inside its 200", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": { status: "failed", error: { message: "no such work" } },
      }),
    }));

    await expect(loadVersions("42")).rejects.toThrow("no such work");
  });
});
