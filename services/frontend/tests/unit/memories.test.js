import { describe, expect, it } from "vitest";

import { localDateString, memoryHeading, parseMemoryGroups } from "../../src/lib/memories.js";

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
