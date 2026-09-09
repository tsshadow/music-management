import { describe, it, expect } from "vitest";
import {
  deduplicateTracks,
  getDeduplicateKey,
  getTrackScore,
  isCanonical,
  versionsOf,
} from "../../src/lib/deduplicate.js";

/**
 * One row per song, from the server's answer rather than from a guess about titles.
 *
 * The rule that decides everything below: what is not understood stays visible. Half the
 * library carries no workId at any moment, and a list that hides those is empty of music
 * that exists — a far worse failure than showing a file twice.
 */

const song = (id, { workId, isCanonical: canonical, versionScore } = {}) => ({
  id: String(id),
  workId,
  isCanonical: canonical,
  versionScore,
});

describe("getDeduplicateKey", () => {
  it("groups the versions of one song", () => {
    expect(getDeduplicateKey(song(1, { workId: 42 }))).toBe(
      getDeduplicateKey(song(2, { workId: 42 })),
    );
  });

  it("gives a track without a work a key of its own", () => {
    expect(getDeduplicateKey(song(1))).not.toBe(getDeduplicateKey(song(2)));
  });

  it("treats a zero or empty work as no work", () => {
    // The column defaults to nothing; a server that has not been told yet must not fold
    // its whole library into one song.
    expect(getDeduplicateKey(song(1, { workId: 0 }))).toBe("track:1");
    expect(getDeduplicateKey(song(2, { workId: "" }))).toBe("track:2");
    expect(getDeduplicateKey(song(3, { workId: null }))).toBe("track:3");
  });
});

describe("isCanonical", () => {
  it("reads the flag however the response spells it", () => {
    expect(isCanonical(song(1, { isCanonical: true }))).toBe(true);
    expect(isCanonical(song(1, { isCanonical: "true" }))).toBe(true);
    expect(isCanonical(song(1, { isCanonical: 1 }))).toBe(true);
    expect(isCanonical(song(1, { isCanonical: false }))).toBe(false);
    expect(isCanonical(song(1, { isCanonical: "false" }))).toBe(false);
  });

  it("treats a missing flag as canonical", () => {
    // An older server, or a response from before migration 118. Reading absence as "not
    // canonical" would hide every track it returns.
    expect(isCanonical(song(1))).toBe(true);
  });
});

describe("deduplicateTracks", () => {
  it("keeps the version the server named", () => {
    const canonical = song(1, { workId: 42, isCanonical: true, versionScore: 10 });
    const other = song(2, { workId: 42, isCanonical: false, versionScore: 9999 });
    expect(deduplicateTracks([other, canonical]).map((t) => t.id)).toEqual(["1"]);
  });

  it("does not let a higher score beat the canonical", () => {
    // The defect this replaces: the old scoring summed its tiers, so a high-bitrate rip
    // outranked an official release.
    const canonical = song(1, { workId: 42, isCanonical: true, versionScore: 0 });
    const rip = song(2, { workId: 42, isCanonical: false, versionScore: 1000000 });
    expect(deduplicateTracks([canonical, rip]).map((t) => t.id)).toEqual(["1"]);
  });

  it("falls back to the score while a work has no canonical yet", () => {
    const worse = song(1, { workId: 42, isCanonical: false, versionScore: 10 });
    const better = song(2, { workId: 42, isCanonical: false, versionScore: 20 });
    expect(deduplicateTracks([worse, better]).map((t) => t.id)).toEqual(["2"]);
  });

  it("keeps every ungrouped track", () => {
    const tracks = [song(1), song(2), song(3)];
    expect(deduplicateTracks(tracks)).toHaveLength(3);
  });

  it("does not show a song again in a later batch", () => {
    const seen = new Map([["work:42", song(1, { workId: 42 })]]);
    expect(deduplicateTracks([song(2, { workId: 42 })], seen)).toEqual([]);
  });

  it("keeps the server's order", () => {
    const tracks = [song(1, { workId: 7 }), song(2, { workId: 8 }), song(3, { workId: 9 })];
    expect(deduplicateTracks(tracks).map((t) => t.id)).toEqual(["1", "2", "3"]);
  });

  it("returns nothing for nothing", () => {
    expect(deduplicateTracks([])).toEqual([]);
  });
});

describe("getTrackScore", () => {
  it("reads the server's score and nothing else", () => {
    expect(getTrackScore(song(1, { versionScore: 1010000 }))).toBe(1010000);
    expect(getTrackScore(song(1, { versionScore: "250" }))).toBe(250);
    expect(getTrackScore(song(1))).toBe(0);
  });
});

describe("versionsOf", () => {
  it("lists the versions of one song, canonical first", () => {
    const tracks = [
      song(1, { workId: 42, isCanonical: false, versionScore: 10 }),
      song(2, { workId: 42, isCanonical: true, versionScore: 5 }),
      song(3, { workId: 42, isCanonical: false, versionScore: 20 }),
      song(4, { workId: 99, isCanonical: true }),
    ];
    expect(versionsOf(tracks, "work:42").map((t) => t.id)).toEqual(["2", "3", "1"]);
  });
});
