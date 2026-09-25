import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { loadSearchFacets, resetSearchFacets } from "../../src/lib/searchFacets.js";
import { credentials } from "../../src/lib/store.js";

/**
 * A Subsonic stand-in answering getGenres / getRecordLabels, with the genre
 * call failing while `failGenres.value` is true.
 */
function api(failGenres) {
  return vi.fn(async (url) => {
    if (url.includes("/rest/getGenres")) {
      if (failGenres.value) throw new Error("offline");
      return {
        json: async () => ({
          "subsonic-response": { status: "ok", genres: { genre: [{ value: "Hardcore" }] } },
        }),
      };
    }
    return {
      json: async () => ({
        "subsonic-response": { status: "ok", recordLabels: { recordLabel: ["Roughstate"] } },
      }),
    };
  });
}

describe("loadSearchFacets", () => {
  beforeEach(() => {
    resetSearchFacets();
    credentials.set({ url: "", username: "user", password: "pw" });
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shares one request between concurrent callers", async () => {
    globalThis.fetch = api({ value: false });
    const [a, b] = await Promise.all([loadSearchFacets(), loadSearchFacets()]);
    expect(a).toEqual({ genres: ["Hardcore"], labels: ["Roughstate"] });
    expect(b).toBe(a);
    expect(globalThis.fetch).toHaveBeenCalledTimes(2);
  });

  it("does not cache a failed list, so the next call retries", async () => {
    const failGenres = { value: true };
    globalThis.fetch = api(failGenres);
    expect(await loadSearchFacets()).toEqual({ genres: [], labels: ["Roughstate"] });
    failGenres.value = false;
    expect((await loadSearchFacets()).genres).toEqual(["Hardcore"]);
  });
});
