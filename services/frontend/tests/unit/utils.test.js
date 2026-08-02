import { beforeEach, describe, expect, it } from "vitest";
import { get } from "svelte/store";

import { mumaApiUrl } from "../../src/lib/store.js";
import { formatArtistList, getArtistImageUrl, splitArtists } from "../../src/lib/utils.js";

describe("splitArtists", () => {
  it("returns nothing for an empty value", () => {
    expect(splitArtists("")).toEqual([]);
    expect(splitArtists(null)).toEqual([]);
    expect(splitArtists(undefined)).toEqual([]);
  });

  it("splits on the separator the tagger writes", () => {
    expect(splitArtists("Angerfist, Outsiders")).toEqual(["Angerfist", "Outsiders"]);
  });

  it("keeps a single artist as one entry", () => {
    expect(splitArtists("Angerfist")).toEqual(["Angerfist"]);
  });

  it("trims the names it produces", () => {
    expect(splitArtists("Angerfist,   Outsiders")).toEqual(["Angerfist", "Outsiders"]);
  });

  it("does not split a name that contains a comma without a space", () => {
    expect(splitArtists("Earth,Wind & Fire")).toEqual(["Earth,Wind & Fire"]);
  });
});

describe("formatArtistList", () => {
  it("returns an empty string for no artists", () => {
    expect(formatArtistList([])).toBe("");
  });

  it("returns a single artist unchanged", () => {
    expect(formatArtistList(["Angerfist"])).toBe("Angerfist");
  });

  it("joins two artists with 'and'", () => {
    expect(formatArtistList(["Angerfist", "Outsiders"])).toBe("Angerfist and Outsiders");
  });

  it("uses commas for all but the last of three or more", () => {
    expect(formatArtistList(["A", "B", "C"])).toBe("A, B and C");
  });
});

describe("getArtistImageUrl", () => {
  beforeEach(() => {
    mumaApiUrl.set("https://muma.test");
  });

  it("prefers the Subsonic cover art when the artist has one", () => {
    const url = getArtistImageUrl({ coverArt: "ar-1", name: "Angerfist", id: 7 }, "u=user&t=x");
    expect(url).toBe("/rest/getCoverArt?id=ar-1&size=300&u=user&t=x");
  });

  it("falls back to the MuMa image endpoint, keyed on the name", () => {
    const url = getArtistImageUrl({ name: "Angerfist", id: 7 }, "u=user");
    expect(url).toBe(`${get(mumaApiUrl)}/api/artists/Angerfist/image?u=user`);
  });

  it("escapes a name that is not URL-safe", () => {
    const url = getArtistImageUrl({ name: "A/B & C" }, "u=user");
    expect(url).toContain(encodeURIComponent("A/B & C"));
  });

  it("falls back to the stored primary image when only an id is known", () => {
    expect(getArtistImageUrl({ id: 7 }, "u=user")).toBe("/media/artist-images/7/primary.jpg");
  });

  it("falls back to the placeholder when nothing identifies the artist", () => {
    expect(getArtistImageUrl({}, "u=user")).toBe("/images/unknown-artist.svg");
    expect(getArtistImageUrl(null, "u=user")).toBe("/images/unknown-artist.svg");
  });
});
