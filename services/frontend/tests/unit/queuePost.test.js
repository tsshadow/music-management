import { describe, it, expect, vi, beforeEach } from "vitest";
import { credentials } from "../../src/lib/store.js";
import { subsonicPost } from "../../src/lib/subsonic.js";
import { saveTracksAsPlaylist } from "../../src/lib/queue.js";

/**
 * A queue travels in a POST body, one parameter per track. Built into the query string, a few
 * hundred tracks made a request line the proxy refused with 414 URI Too Long.
 */

const ok = () => ({ ok: true, json: async () => ({ "subsonic-response": { status: "ok" } }) });
const manyTracks = (n) => Array.from({ length: n }, (_, i) => ({ id: `tr-${1000 + i}` }));

describe("subsonicPost", () => {
  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "user", password: "pw" });
  });

  it("puts the fields in a form body and only the credentials in the URL", async () => {
    const fetchImpl = vi.fn(async () => ok());

    await subsonicPost(
      "savePlayQueue",
      [
        ["id", "a"],
        ["id", "b"],
        ["current", "b"],
        ["playing", true],
        ["position", undefined],
      ],
      "u=user&t=x",
      { fetchImpl },
    );

    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("https://lms.example/rest/savePlayQueue?u=user&t=x");
    expect(init.method).toBe("POST");
    expect(init.body).toBeInstanceOf(URLSearchParams);
    expect(init.body.getAll("id")).toEqual(["a", "b"]);
    expect(init.body.get("current")).toBe("b");
    expect(init.body.get("playing")).toBe("true");
    expect(init.body.has("position")).toBe(false);
  });
});

describe("saveTracksAsPlaylist", () => {
  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "user", password: "pw" });
  });

  it("sends a long queue in the body, keeping the URL short", async () => {
    const fetchImpl = vi.fn(async () => ok());
    const tracks = manyTracks(2000);

    await saveTracksAsPlaylist("Road trip", tracks, "u=user&t=x", { fetchImpl });

    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe("https://lms.example/rest/createPlaylist?u=user&t=x");
    expect(url.length).toBeLessThan(200);
    expect(init.method).toBe("POST");
    expect(init.body.get("name")).toBe("Road trip");
    expect(init.body.getAll("songId")).toEqual(tracks.map((t) => t.id));
  });

  it("throws when the server refuses in the Subsonic envelope", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": { status: "failed", error: { code: 10, message: "missing" } },
      }),
    }));

    await expect(saveTracksAsPlaylist("x", manyTracks(1), "u=user", { fetchImpl })).rejects.toThrow(
      "missing",
    );
  });

  it("throws on an HTTP failure", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: false, status: 414, statusText: "URI Too Long" }));

    await expect(saveTracksAsPlaylist("x", manyTracks(1), "u=user", { fetchImpl })).rejects.toThrow(
      "URI Too Long",
    );
  });
});
