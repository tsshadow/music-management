import { describe, it, expect, vi, beforeEach } from "vitest";
import { credentials, subsonicToken } from "../../src/lib/store.js";
import { loadTopArtists, loadTopLabels, resolveArtistView } from "../../src/lib/homeRankings.js";

/** A fetcher answering with `body`, `ok` by default. */
function fetcherAnswering(body, { ok = true } = {}) {
  return vi.fn(async () => ({ ok, json: async () => body }));
}

describe("loadTopArtists", () => {
  it("maps rows to {name, listens}", async () => {
    const fetcher = fetcherAnswering({
      unmatched: 3,
      artists: [
        { artist_id: 1, artist: "Angerfist", listens: 40, tracks: 12, estimated_secs: 9000 },
        { artist_id: 2, artist: "Frequencerz", listens: 15, tracks: 5, estimated_secs: 3000 },
      ],
    });

    const artists = await loadTopArtists(fetcher);

    expect(artists).toEqual([
      { name: "Angerfist", listens: 40 },
      { name: "Frequencerz", listens: 15 },
    ]);
  });

  it("resolves to [] on a non-OK response, rather than throwing", async () => {
    const fetcher = fetcherAnswering(
      { artists: [{ artist: "Angerfist", listens: 40 }] },
      { ok: false },
    );

    expect(await loadTopArtists(fetcher)).toEqual([]);
  });

  it("resolves to [] when the request never reaches a server", async () => {
    const fetcher = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });

    expect(await loadTopArtists(fetcher)).toEqual([]);
  });

  it("resolves to [] when the body has no artists field", async () => {
    const fetcher = fetcherAnswering({ unmatched: 0 });

    expect(await loadTopArtists(fetcher)).toEqual([]);
  });
});

describe("loadTopLabels", () => {
  it("maps rows to {name, listens}", async () => {
    const fetcher = fetcherAnswering({
      unmatched: 1,
      labels: [{ label_id: 9, label: "Art of Creation", listens: 22, tracks: 6 }],
    });

    expect(await loadTopLabels(fetcher)).toEqual([{ name: "Art of Creation", listens: 22 }]);
  });

  it("resolves to [] on a 500", async () => {
    const fetcher = fetcherAnswering({}, { ok: false });

    expect(await loadTopLabels(fetcher)).toEqual([]);
  });

  it("resolves to [] on a network error", async () => {
    const fetcher = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });

    expect(await loadTopLabels(fetcher)).toEqual([]);
  });
});

describe("resolveArtistView", () => {
  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "demo-user", password: "pw" });
    subsonicToken.set({ username: "demo-user", token: "test-subsonic-token" });
  });

  /** A search3 response carrying the given artist entries. */
  function searchResultWith(artists) {
    return {
      ok: true,
      json: async () => ({
        "subsonic-response": { status: "ok", searchResult3: { artist: artists } },
      }),
    };
  }

  it("returns artist:<id> for the entry matching the name, case-insensitively", async () => {
    globalThis.fetch = vi.fn(async () =>
      searchResultWith([
        { id: "77", name: "Angerfist Live" },
        { id: "12", name: "angerfist" },
      ]),
    );

    expect(await resolveArtistView("Angerfist")).toBe("artist:12");
  });

  it("falls back to the first result when nothing matches the name exactly", async () => {
    globalThis.fetch = vi.fn(async () => searchResultWith([{ id: "5", name: "Angerfist Live" }]));

    expect(await resolveArtistView("Angerfist Unique Query")).toBe("artist:5");
  });

  it("resolves to null when search3 finds no artists", async () => {
    globalThis.fetch = vi.fn(async () => searchResultWith([]));

    expect(await resolveArtistView("Nobody Known")).toBeNull();
  });

  it("resolves to null rather than throwing when the request fails", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });

    expect(await resolveArtistView("Broken Query")).toBeNull();
  });

  it("memoises per name: a second call does not fetch again", async () => {
    const fetch = vi.fn(async () => searchResultWith([{ id: "1", name: "Repeated Artist" }]));
    globalThis.fetch = fetch;

    const first = await resolveArtistView("Repeated Artist");
    const second = await resolveArtistView("Repeated Artist");

    expect(first).toBe("artist:1");
    expect(second).toBe("artist:1");
    expect(fetch).toHaveBeenCalledTimes(1);
  });

  it("shares one in-flight request between concurrent calls for the same name", async () => {
    let resolveFetch;
    const fetch = vi.fn(
      () =>
        new Promise((resolve) => {
          resolveFetch = () => resolve(searchResultWith([{ id: "9", name: "Concurrent Artist" }]));
        }),
    );
    globalThis.fetch = fetch;

    const first = resolveArtistView("Concurrent Artist");
    const second = resolveArtistView("Concurrent Artist");
    resolveFetch();

    expect(await first).toBe("artist:9");
    expect(await second).toBe("artist:9");
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
