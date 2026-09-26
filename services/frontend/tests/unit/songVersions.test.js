import { describe, it, expect, vi, afterEach } from "vitest";
import {
  curationQuery,
  pageCount,
  formatLabel,
  isChanged,
  uniqueTracks,
  songVersionsApi,
} from "../../src/lib/management/songVersions.js";

describe("curationQuery", () => {
  it("sends the defaults when nothing is chosen", () => {
    expect(curationQuery()).toBe("sort=versions&page=1&page_size=50");
  });

  it("carries the search, the sort and the changed filter", () => {
    const query = new URLSearchParams(
      curationQuery({ q: "  fist ", sort: "changed", changedOnly: true, page: 3 }),
    );
    expect(query.get("q")).toBe("fist");
    expect(query.get("sort")).toBe("changed");
    expect(query.get("changed_only")).toBe("true");
    expect(query.get("page")).toBe("3");
  });

  it("falls back to the default sort for anything unknown", () => {
    expect(new URLSearchParams(curationQuery({ sort: "id;DROP" })).get("sort")).toBe("versions");
  });

  it("never asks for a page before the first", () => {
    expect(new URLSearchParams(curationQuery({ page: 0 })).get("page")).toBe("1");
  });
});

describe("pageCount", () => {
  it("is at least one page", () => {
    expect(pageCount(0)).toBe(1);
  });

  it("rounds up", () => {
    expect(pageCount(101, 50)).toBe(3);
  });
});

describe("formatLabel", () => {
  it("leaves the bitrate off a lossless file", () => {
    expect(formatLabel({ format: "flac", bitrate_kbps: 912 })).toBe("FLAC");
  });

  it("snaps a derived bitrate to the encoder setting", () => {
    expect(formatLabel({ format: "mp3", bitrate_kbps: 327 })).toBe("MP3 320");
    expect(formatLabel({ format: "m4a", bitrate_kbps: 131 })).toBe("M4A 128");
  });

  it("keeps an unusual bitrate as it is", () => {
    expect(formatLabel({ format: "mp3", bitrate_kbps: 224 })).toBe("MP3 224");
  });

  it("is empty without a file", () => {
    expect(formatLabel({ format: null })).toBe("");
  });
});

describe("isChanged", () => {
  it("is true only while the rescore flag is set", () => {
    expect(isChanged({ canonical_changed_at: "2026-09-26T10:00:00" })).toBe(true);
    expect(isChanged({ canonical_changed_at: null })).toBe(false);
  });
});

describe("uniqueTracks", () => {
  it("keeps the first row of a track that has several files", () => {
    const rows = [
      { track_id: 1, format: "flac" },
      { track_id: 1, format: "mp3" },
      { track_id: 2, format: "mp3" },
    ];
    expect(uniqueTracks(rows).map((row) => row.format)).toEqual(["flac", "mp3"]);
  });
});

describe("songVersionsApi", () => {
  afterEach(() => vi.restoreAllMocks());

  it("pins with the track id and resets with null", async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ status: "ok" }) }));
    const api = songVersionsApi("http://muma", () => ({ "x-api-key": "k" }));
    await api.pin(5, 22);
    await api.pin(5, null);
    const bodies = globalThis.fetch.mock.calls.map(([, options]) => JSON.parse(options.body));
    expect(bodies).toEqual([{ track_id: 22 }, { track_id: null }]);
    expect(globalThis.fetch.mock.calls[0][0]).toBe("http://muma/api/songs/5/pin");
  });

  it("reports the server's reason when a write is refused", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 403,
      json: async () => ({ detail: "Missing permission: rules.manage" }),
    }));
    const api = songVersionsApi("http://muma", () => ({}));
    await expect(api.dismissChange(5)).rejects.toThrow("Missing permission: rules.manage");
  });
});
