import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchTrackDetails } from "../../src/lib/trackDetails.js";

vi.mock("../../src/lib/mumaApi.js", () => ({
  apiBase: () => "http://muma",
  gatedFetch: (...args) => globalThis.__gatedFetch(...args),
  getHeaders: () => ({ "X-API-Key": "the-users-key" }),
}));

describe("fetchTrackDetails", () => {
  beforeEach(() => {
    globalThis.__gatedFetch = vi.fn();
  });

  it("asks MuMa by the LMS-relative path, with the user's key", async () => {
    globalThis.__gatedFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ tags: {} }),
    });

    const result = await fetchTrackDetails("Soundcloud/Complex/a & b.mp3");

    expect(globalThis.__gatedFetch).toHaveBeenCalledWith(
      "http://muma/api/library/tracks/by-path?path=Soundcloud%2FComplex%2Fa%20%26%20b.mp3",
      { headers: { "X-API-Key": "the-users-key" } },
    );
    expect(result).toEqual({ state: "ok", details: { tags: {} } });
  });

  it("reads a 404 as MuMa never having scanned the file, not as an error", async () => {
    globalThis.__gatedFetch.mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: "nope" }),
    });
    expect(await fetchTrackDetails("x.mp3")).toEqual({ state: "none", details: null });
  });

  it("reads any other failure as MuMa being unreachable", async () => {
    globalThis.__gatedFetch.mockResolvedValue({ ok: false, status: 503, json: async () => ({}) });
    expect(await fetchTrackDetails("x.mp3")).toEqual({ state: "error", details: null });

    globalThis.__gatedFetch.mockRejectedValue(new Error("gate refused"));
    expect(await fetchTrackDetails("x.mp3")).toEqual({ state: "error", details: null });
  });

  it("does not ask at all without a path", async () => {
    expect(await fetchTrackDetails("")).toEqual({ state: "none", details: null });
    expect(globalThis.__gatedFetch).not.toHaveBeenCalled();
  });
});
