import { describe, it, expect, vi, afterEach } from "vitest";
import { loadIndexedTags } from "../../src/lib/scanTags.js";

function respond(body) {
  return vi.fn(async () => ({ ok: true, json: async () => body }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("loadIndexedTags", () => {
  it("returns the extra tags an admin is told about", async () => {
    vi.stubGlobal(
      "fetch",
      respond({
        "subsonic-response": {
          scanStatus: { scanSettings: { extraTagsToScan: { value: ["FESTIVAL", "PODCAST"] } } },
        },
      }),
    );

    expect(await loadIndexedTags("u=user")).toEqual(["FESTIVAL", "PODCAST"]);
  });

  it("accepts a single tag that the server did not wrap in an array", async () => {
    vi.stubGlobal(
      "fetch",
      respond({
        "subsonic-response": {
          scanStatus: { scanSettings: { extraTagsToScan: { value: "FESTIVAL" } } },
        },
      }),
    );

    expect(await loadIndexedTags("u=user")).toEqual(["FESTIVAL"]);
  });

  // A non-admin gets a scanStatus without any scanSettings at all. Reading that as
  // "no tags are indexed" would show every listener a diagnostic about a server
  // setting they cannot see, let alone change.
  it("answers null when the response carries no settings, as it does for a non-admin", async () => {
    vi.stubGlobal("fetch", respond({ "subsonic-response": { scanStatus: { scanning: false } } }));

    expect(await loadIndexedTags("u=user")).toBeNull();
  });

  it("answers null when the request fails rather than throwing at the caller", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("offline");
      }),
    );

    expect(await loadIndexedTags("u=user")).toBeNull();
  });

  it("answers null without calling the server when there is no session yet", async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal("fetch", fetchSpy);

    expect(await loadIndexedTags("")).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
