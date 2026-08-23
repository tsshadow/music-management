import { describe, expect, it } from "vitest";

import {
  localDateString,
  memoriesUrl,
  memoryHeading,
  parseMemoryGroups,
  rankSongs,
  yearTiles,
} from "../../src/lib/memories.js";

describe("localDateString", () => {
  it("formats a date as yyyy-MM-dd with padding", () => {
    expect(localDateString(new Date(2026, 7, 2))).toBe("2026-08-02");
    expect(localDateString(new Date(2026, 11, 25))).toBe("2026-12-25");
  });

  it("reports the local day, not the UTC one", () => {
    // Late evening in a positive-offset zone is already the next day in UTC; the memories of
    // "today" must follow the device, so this may never roll over to the 3rd.
    const lateEvening = new Date(2026, 7, 2, 23, 30);
    expect(localDateString(lateEvening)).toBe("2026-08-02");
  });
});

describe("memoriesUrl", () => {
  it("asks for the whole year rather than the server's page", () => {
    expect(memoriesUrl("u=user&p=pw", "2026-08-23")).toBe(
      "/rest/getMemories?date=2026-08-23&maxPerYear=200&u=user&p=pw",
    );
  });

  it("falls back to the device's own today", () => {
    expect(memoriesUrl("u=user")).toContain(`date=${localDateString()}`);
  });
});

describe("parseMemoryGroups", () => {
  const wrap = (memory) => ({ "subsonic-response": { memories: { memory } } });

  it("returns nothing for an empty or absent memories node", () => {
    expect(parseMemoryGroups({ "subsonic-response": { memories: {} } })).toEqual([]);
    expect(parseMemoryGroups({ "subsonic-response": {} })).toEqual([]);
    expect(parseMemoryGroups({})).toEqual([]);
    expect(parseMemoryGroups(undefined)).toEqual([]);
  });

  it("keeps the server's group order", () => {
    const groups = parseMemoryGroups(
      wrap([
        { year: 2018, yearsAgo: 8, exact: true, song: [{ id: "1" }, { id: "2" }] },
        { year: 2015, yearsAgo: 11, exact: false, song: [{ id: "3" }] },
      ]),
    );

    expect(groups.map((g) => g.year)).toEqual([2018, 2015]);
    expect(groups[0].songs.map((s) => s.id)).toEqual(["1", "2"]);
  });

  it("coerces a lone group back into a list", () => {
    const groups = parseMemoryGroups(wrap({ year: 2018, yearsAgo: 8, exact: true, song: [{ id: "1" }] }));

    expect(groups).toHaveLength(1);
    expect(groups[0].year).toBe(2018);
  });

  it("coerces a lone song back into a list", () => {
    const groups = parseMemoryGroups(wrap([{ year: 2018, yearsAgo: 8, exact: true, song: { id: "1" } }]));

    expect(groups[0].songs).toEqual([{ id: "1" }]);
  });

  it("gives a group without songs an empty list rather than undefined", () => {
    const groups = parseMemoryGroups(wrap([{ year: 2018, yearsAgo: 8, exact: true }]));

    expect(groups[0].songs).toEqual([]);
  });
});

describe("memoryHeading", () => {
  it("says today only when the group really falls on today", () => {
    expect(memoryHeading({ exact: true, yearsAgo: 8 })).toEqual({
      key: "memories.today",
      vars: { count: 8 },
    });
  });

  it("says this week for a group that only matched the surrounding days", () => {
    expect(memoryHeading({ exact: false, yearsAgo: 11 })).toEqual({
      key: "memories.thisWeek",
      vars: { count: 11 },
    });
  });

  it("passes the age as count, so the translation can pluralise", () => {
    expect(memoryHeading({ exact: true, yearsAgo: 1 }).vars).toEqual({ count: 1 });
  });
});

describe("rankSongs", () => {
  const song = (id, { userRating, playCount, title } = {}) => ({
    id,
    title: title ?? `Track ${id}`,
    ...(userRating === undefined ? {} : { userRating }),
    ...(playCount === undefined ? {} : { playCount }),
  });

  it("puts favourites ahead of everything else", () => {
    const ranked = rankSongs([song("a", { playCount: 90 }), song("b", { userRating: 5, playCount: 2 })]);

    expect(ranked.map((s) => s.id)).toEqual(["b", "a"]);
  });

  it("orders favourites among themselves by listens", () => {
    const ranked = rankSongs([
      song("a", { userRating: 5, playCount: 3 }),
      song("b", { userRating: 5, playCount: 12 }),
    ]);

    expect(ranked.map((s) => s.id)).toEqual(["b", "a"]);
  });

  it("falls back to listens for the rest", () => {
    const ranked = rankSongs([
      song("a", { userRating: 4, playCount: 1 }),
      song("b", { playCount: 7 }),
      song("c", { userRating: 3, playCount: 4 }),
    ]);

    expect(ranked.map((s) => s.id)).toEqual(["b", "c", "a"]);
  });

  it("breaks a tie on listens with the rating, then the title", () => {
    const ranked = rankSongs([
      song("a", { playCount: 4, title: "Beta" }),
      song("b", { playCount: 4, userRating: 2, title: "Zulu" }),
      song("c", { playCount: 4, title: "Alpha" }),
    ]);

    expect(ranked.map((s) => s.id)).toEqual(["b", "c", "a"]);
  });

  it("treats a missing rating or play count as zero", () => {
    const ranked = rankSongs([song("a"), song("b", { playCount: 1 })]);

    expect(ranked.map((s) => s.id)).toEqual(["b", "a"]);
  });

  it("leaves the caller's array untouched", () => {
    const songs = [song("a", { playCount: 1 }), song("b", { playCount: 9 })];
    rankSongs(songs);

    expect(songs.map((s) => s.id)).toEqual(["a", "b"]);
  });
});

describe("yearTiles", () => {
  const group = (year, songs, { yearsAgo = 1, exact = true } = {}) => ({ year, yearsAgo, exact, songs });
  const song = (id, playCount) => ({ id, title: `Track ${id}`, coverArt: `art-${id}`, playCount });

  it("carries the group's own facts through", () => {
    const [tile] = yearTiles([group(2025, [song("a", 1)], { yearsAgo: 1, exact: false })]);

    expect(tile).toMatchObject({ year: 2025, yearsAgo: 1, exact: false, count: 1 });
  });

  it("counts every song in the group, not just the ones on the tile", () => {
    const songs = Array.from({ length: 9 }, (_, i) => song(String(i), i));
    const [tile] = yearTiles([group(2025, songs)]);

    expect(tile.count).toBe(9);
    expect(tile.top).toHaveLength(3);
  });

  it("shows the most popular three, best first", () => {
    const [tile] = yearTiles([group(2025, [song("a", 2), song("b", 40), song("c", 9), song("d", 30)])]);

    expect(tile.top.map((s) => s.id)).toEqual(["b", "d", "c"]);
  });

  it("takes four covers for the collage, skipping songs without one", () => {
    const [tile] = yearTiles([
      group(2025, [{ id: "a", playCount: 5 }, song("b", 4), song("c", 3), song("d", 2), song("e", 1)]),
    ]);

    expect(tile.covers).toEqual(["art-b", "art-c", "art-d", "art-e"]);
  });

  it("keeps the server's year order", () => {
    const tiles = yearTiles([group(2025, [song("a", 1)]), group(2019, [song("b", 1)])]);

    expect(tiles.map((t) => t.year)).toEqual([2025, 2019]);
  });

  it("drops a year that has no songs at all", () => {
    expect(yearTiles([group(2025, [])])).toEqual([]);
  });
});
