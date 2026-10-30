import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { artistImageFallback, missingArtistImages } from "../../src/lib/coverArt.js";
import { mumaApiUrl } from "../../src/lib/store.js";

/**
 * What a track without a cover falls back to: its first artist's portrait, unless MuMa has
 * already said (with a 404 this session) that there is none.
 */
describe("artistImageFallback", () => {
  beforeEach(() => {
    mumaApiUrl.set("https://muma.test");
  });

  afterEach(() => {
    missingArtistImages.clear();
  });

  it("points at the first artist's portrait", () => {
    const url = artistImageFallback(
      { artist: "Angerfist, Outsiders", artistId: "a-1" },
      "u=demo-user",
    );
    expect(url).toBe("https://muma.test/api/artists/Angerfist/image?u=demo-user");
  });

  it("prefers the artists array over the joined string", () => {
    const url = artistImageFallback(
      { artist: "Angerfist,Outsiders", artists: [{ id: "a-1", name: "Angerfist" }] },
      "u=demo-user",
    );
    expect(url).toBe("https://muma.test/api/artists/Angerfist/image?u=demo-user");
  });

  it("has nothing for a track without an artist", () => {
    expect(artistImageFallback({ artist: "", artistId: null }, "u=demo-user")).toBeNull();
    expect(artistImageFallback(null, "u=demo-user")).toBeNull();
  });

  it("never hands out the unknown-artist placeholder as if it were a portrait", () => {
    // An artists entry with neither a name nor an id resolves to the placeholder path.
    expect(artistImageFallback({ artists: [{ name: "" }], artist: "" }, "u=demo-user")).toBeNull();
  });

  it("answers null once a portrait URL is known to be missing", () => {
    const track = { artist: "Angerfist", artistId: "a-1" };
    const url = artistImageFallback(track, "u=demo-user");
    missingArtistImages.add(url);

    expect(artistImageFallback(track, "u=demo-user")).toBeNull();
  });
});
