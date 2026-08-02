import { describe, expect, it } from "vitest";

import {
  deduplicateTracks,
  getDeduplicateKey,
  getTrackScore,
  normalizeArtist,
  normalizeTitle,
} from "../../src/lib/deduplicate.js";

describe("normalizeArtist", () => {
  it("returns an empty key for nothing", () => {
    expect(normalizeArtist("")).toBe("");
    expect(normalizeArtist(null)).toBe("");
    expect(normalizeArtist(undefined)).toBe("");
  });

  it("lowercases and trims", () => {
    expect(normalizeArtist("  Angerfist  ")).toBe("angerfist");
  });

  it("treats the collaboration separators as equivalent", () => {
    const expected = "angerfist|outsiders";
    expect(normalizeArtist("Angerfist, Outsiders")).toBe(expected);
    expect(normalizeArtist("Angerfist & Outsiders")).toBe(expected);
    expect(normalizeArtist("Angerfist feat. Outsiders")).toBe(expected);
    expect(normalizeArtist("Angerfist ft Outsiders")).toBe(expected);
    expect(normalizeArtist("Angerfist and Outsiders")).toBe(expected);
  });

  it("ignores the order the artists are listed in", () => {
    expect(normalizeArtist("Outsiders & Angerfist")).toBe(normalizeArtist("Angerfist & Outsiders"));
  });

  it("drops empty segments left by a trailing separator", () => {
    expect(normalizeArtist("Angerfist & ")).toBe("angerfist");
  });
});

describe("normalizeTitle", () => {
  it("returns an empty key for nothing", () => {
    expect(normalizeTitle("")).toBe("");
    expect(normalizeTitle(null)).toBe("");
  });

  it("lowercases and trims", () => {
    expect(normalizeTitle("  Raise Your Fist  ")).toBe("raise your fist");
  });

  it("collapses the version suffixes onto the same key", () => {
    const base = normalizeTitle("Raise Your Fist");
    expect(normalizeTitle("Raise Your Fist (Radio Edit)")).toBe(base);
    expect(normalizeTitle("Raise Your Fist (Extended Mix)")).toBe(base);
    expect(normalizeTitle("Raise Your Fist (Original Mix)")).toBe(base);
  });
});

describe("getTrackScore", () => {
  it("prefers lossless over anything else", () => {
    const flac = getTrackScore({ suffix: "flac", title: "x" });
    const mp3 = getTrackScore({ suffix: "mp3", bitRate: 320, title: "x" });
    const m4a = getTrackScore({ suffix: "m4a", title: "x" });
    expect(flac).toBeGreaterThan(mp3);
    expect(mp3).toBeGreaterThan(m4a);
  });

  it("ranks mp3 by bitrate", () => {
    const high = getTrackScore({ suffix: "mp3", bitRate: 320, title: "x" });
    const middle = getTrackScore({ suffix: "mp3", bitRate: 192, title: "x" });
    const low = getTrackScore({ suffix: "mp3", bitRate: 128, title: "x" });
    const unknown = getTrackScore({ suffix: "mp3", title: "x" });
    expect(high).toBeGreaterThan(middle);
    expect(middle).toBeGreaterThan(low);
    expect(low).toBeGreaterThan(unknown);
  });

  it("prefers a radio edit, then the default, then an original mix, then extended", () => {
    const score = (title) => getTrackScore({ suffix: "flac", title });
    expect(score("Track (Radio Edit)")).toBeGreaterThan(score("Track (Original Mix)"));
    expect(score("Track (Original Mix)")).toBeGreaterThan(score("Track"));
    expect(score("Track")).toBeGreaterThan(score("Track (Extended Mix)"));
  });

  it("scores a track with no metadata at all rather than throwing", () => {
    expect(getTrackScore({})).toBeGreaterThan(0);
  });

  it("is case-insensitive about the format and the version", () => {
    expect(getTrackScore({ suffix: "FLAC", title: "Track (RADIO EDIT)" }))
      .toBe(getTrackScore({ suffix: "flac", title: "track (radio edit)" }));
  });
});

describe("getDeduplicateKey", () => {
  it("puts two versions of the same track on the same key", () => {
    const first = { artist: "Angerfist", title: "Raise Your Fist (Radio Edit)" };
    const second = { artist: "Angerfist", title: "Raise Your Fist (Extended Mix)" };
    expect(getDeduplicateKey(first)).toBe(getDeduplicateKey(second));
  });

  it("keeps different tracks apart", () => {
    const first = { artist: "Angerfist", title: "Raise Your Fist" };
    const second = { artist: "Angerfist", title: "Incoming" };
    expect(getDeduplicateKey(first)).not.toBe(getDeduplicateKey(second));
  });

  it("keeps the same title by a different artist apart", () => {
    const first = { artist: "Angerfist", title: "Bloodrush" };
    const second = { artist: "Radical Redemption", title: "Bloodrush" };
    expect(getDeduplicateKey(first)).not.toBe(getDeduplicateKey(second));
  });
});

describe("deduplicateTracks", () => {
  const flac = { id: 1, artist: "Angerfist", title: "Raise Your Fist", suffix: "flac" };
  const mp3 = { id: 2, artist: "Angerfist", title: "Raise Your Fist (Extended Mix)", suffix: "mp3", bitRate: 192 };
  const other = { id: 3, artist: "Angerfist", title: "Incoming", suffix: "mp3", bitRate: 320 };

  it("keeps the best version of a duplicated track", () => {
    expect(deduplicateTracks([mp3, flac])).toEqual([flac]);
  });

  it("does not depend on the input order", () => {
    expect(deduplicateTracks([flac, mp3])).toEqual([flac]);
  });

  it("leaves distinct tracks alone", () => {
    const result = deduplicateTracks([flac, other]);
    expect(result).toHaveLength(2);
    expect(result.map((track) => track.id).sort()).toEqual([1, 3]);
  });

  it("returns nothing for an empty list", () => {
    expect(deduplicateTracks([])).toEqual([]);
  });

  it("skips a track already shown in an earlier batch", () => {
    const seen = new Map([[getDeduplicateKey(flac), flac]]);
    expect(deduplicateTracks([mp3, other], seen)).toEqual([other]);
  });

  it("does not mutate the list it was given", () => {
    const tracks = [mp3, flac];
    deduplicateTracks(tracks);
    expect(tracks).toEqual([mp3, flac]);
  });
});
