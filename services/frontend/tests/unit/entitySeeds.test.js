import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  openSong,
  songSeedFromTrack,
  MAX_SEEDS,
  albumSeedFromTrack,
  artistSeedFromTrack,
  clearSeeds,
  openEntity,
  peekSeed,
  pressEntity,
  registerPagePreloader,
  registerPrefetcher,
  seedEntity,
  seedFromTrack,
} from "../../src/lib/entitySeeds.js";

/** What a link leaves for the page it opens (docs/designs/perceived-performance/). */
describe("entitySeeds", () => {
  beforeEach(() => {
    clearSeeds();
  });

  it("opening an entity seeds it and navigates to its view", () => {
    const navigate = vi.fn();

    openEntity(navigate, "artist", { id: 42, name: "Angerfist", coverArt: "ar-42", extra: "x" });

    expect(navigate).toHaveBeenCalledWith("artist:42");
    expect(peekSeed("artist", 42)).toEqual({ name: "Angerfist", coverArt: "ar-42" });
  });

  it("does nothing for an entity without an id", () => {
    const navigate = vi.fn();

    openEntity(navigate, "artist", { name: "Nobody" });

    expect(navigate).not.toHaveBeenCalled();
  });

  it("never lets a poorer link erase what a richer one left", () => {
    seedEntity("album", "7", { name: "Close Combat", coverArt: "al-7", year: 2008 });
    seedEntity("album", "7", { name: "", coverArt: null, artist: "Angerfist" });

    expect(peekSeed("album", "7")).toEqual({
      name: "Close Combat",
      coverArt: "al-7",
      year: 2008,
      artist: "Angerfist",
    });
  });

  it("has nothing for an id no link seeded", () => {
    expect(peekSeed("artist", "unknown")).toBeNull();
  });

  it("keeps a bounded number of seeds, oldest going first", () => {
    for (let i = 0; i <= MAX_SEEDS; i++) seedEntity("artist", i, { name: `A${i}` });

    expect(peekSeed("artist", 0)).toBeNull();
    expect(peekSeed("artist", MAX_SEEDS)).toEqual({ name: `A${MAX_SEEDS}` });
  });

  it("takes a track's first credited artist, with the name shown for that id", () => {
    expect(
      artistSeedFromTrack({
        artists: [
          { id: 3, name: "Miss K8" },
          { id: 4, name: "MC Nolz" },
        ],
      }),
    ).toEqual({ id: "3", seed: { name: "Miss K8" } });
    // A legacy comma-joined credit: the id belongs to the first name only, as in ArtistList.
    expect(artistSeedFromTrack({ artistId: 5, artist: "Angerfist, Outsiders" })).toEqual({
      id: "5",
      seed: { name: "Angerfist" },
    });
    expect(artistSeedFromTrack({ artist: "No id" })).toBeNull();
  });

  it("takes a track's album with its cover and album artist", () => {
    expect(
      albumSeedFromTrack({
        albumId: 9,
        album: "Close Combat",
        coverArt: "al-9",
        artist: "Angerfist, Outsiders",
        albumArtist: "Angerfist",
        year: 2008,
      }),
    ).toEqual({
      id: "9",
      seed: { name: "Close Combat", coverArt: "al-9", artist: "Angerfist", year: 2008 },
    });
    expect(albumSeedFromTrack({ album: "No id" })).toBeNull();
  });

  it("seeds both the artist and the album from a track", () => {
    seedFromTrack({ artistId: 5, artist: "Angerfist", albumId: 9, album: "Close Combat" });

    expect(peekSeed("artist", "5")).toEqual({ name: "Angerfist" });
    expect(peekSeed("album", "9")).toMatchObject({ name: "Close Combat" });
  });

  it("a press seeds the entity and starts its registered prefetch once", () => {
    const prefetch = vi.fn(async () => ({}));
    registerPrefetcher("test-kind", prefetch);

    pressEntity("test-kind", { id: 12, name: "Pressed" });

    expect(prefetch).toHaveBeenCalledTimes(1);
    expect(prefetch).toHaveBeenCalledWith("12");
    expect(peekSeed("test-kind", 12)).toEqual({ name: "Pressed" });
  });

  it("a failing prefetch never breaks the press it rides on", () => {
    registerPrefetcher("throws", () => {
      throw new Error("boom");
    });
    registerPrefetcher("rejects", () => Promise.reject(new Error("boom")));

    expect(() => pressEntity("throws", { id: 1 })).not.toThrow();
    expect(() => pressEntity("rejects", { id: 1 })).not.toThrow();
  });
});

describe("song seeds (issue #111)", () => {
  beforeEach(() => clearSeeds());

  it("seeds the versions page with the row's title, artist and cover, then navigates", () => {
    const navigate = vi.fn();
    openSong(navigate, {
      workId: 7,
      title: "Raise Your Fist",
      artist: "Angerfist",
      artistId: "ar-1",
      coverArt: "al-1",
    });

    expect(navigate).toHaveBeenCalledWith("song:7");
    expect(peekSeed("song", "7")).toEqual({
      name: "Raise Your Fist",
      artist: "Angerfist",
      artistId: "ar-1",
      coverArt: "al-1",
    });
  });

  it("does nothing for a track without a work id", () => {
    const navigate = vi.fn();
    openSong(navigate, { title: "Loose file" });

    expect(songSeedFromTrack({ title: "Loose file" })).toBeNull();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("a press also starts the kind's page chunk, and a failing one never breaks the press", () => {
    const preload = vi.fn(() => Promise.resolve({}));
    registerPagePreloader("chunk-kind", preload);
    registerPagePreloader("chunk-throws", () => {
      throw new Error("boom");
    });
    registerPagePreloader("chunk-rejects", () => Promise.reject(new Error("offline")));

    pressEntity("chunk-kind", { id: 3, name: "Pressed" });

    expect(preload).toHaveBeenCalledTimes(1);
    expect(() => pressEntity("chunk-throws", { id: 1 })).not.toThrow();
    expect(() => pressEntity("chunk-rejects", { id: 1 })).not.toThrow();
  });

  it("the artist, album and feed pages register their chunks for a press (issue #118)", async () => {
    const { lazyViews } = await import("../../src/lib/lazyViews.js");
    const load = vi.spyOn(lazyViews, "load").mockResolvedValue({});

    pressEntity("artist", { id: "ar-1", name: "Angerfist" });
    pressEntity("album", { id: "al-1", name: "Mutilate" });
    pressEntity("feed", { id: "release-radar", name: "Release Radar" });

    expect(load.mock.calls.map(([name]) => name)).toEqual(
      expect.arrayContaining(["artistPage", "albumPage", "feedPage"]),
    );
    load.mockRestore();
  });
});
