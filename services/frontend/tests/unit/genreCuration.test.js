import { describe, it, expect } from "vitest";
import {
  WHITE,
  BLACK,
  UNKNOWN,
  normalizeGenre,
  filterGenres,
  summarize,
  describeOutcome,
  describeDecision,
  buildDecision,
  correctionTargets,
} from "../../src/lib/management/genreCuration";

const row = (over = {}) => ({
  id: 1,
  name: "Hardstyle",
  state: WHITE,
  canonical_targets: [],
  occurrences: 0,
  decided_at: null,
  decided_by: null,
  ...over,
});

describe("normalizeGenre", () => {
  it("lowercases and collapses punctuation", () => {
    expect(normalizeGenre("Uptempo-Hardcore")).toBe("uptempo hardcore");
  });

  it("strips accents so spelling variants share a key", () => {
    expect(normalizeGenre("Électro")).toBe("electro");
  });

  it("keeps separators as a space, matching the backend key", () => {
    // 'hard style' and 'hardstyle' really are two different genres to the tagger;
    // the search box must not pretend otherwise.
    expect(normalizeGenre("hard-style")).not.toBe(normalizeGenre("Hardstyle"));
  });

  it("returns an empty key for names without any alphanumerics", () => {
    expect(normalizeGenre("   ")).toBe("");
    expect(normalizeGenre(null)).toBe("");
  });
});

describe("filterGenres", () => {
  const rows = [row({ id: 1, name: "Hardstyle" }), row({ id: 2, name: "Uptempo Hardcore" })];

  it("returns everything when the query is empty", () => {
    expect(filterGenres(rows, "")).toHaveLength(2);
  });

  it("matches regardless of casing and accents", () => {
    expect(filterGenres(rows, "HÁRDSTYLE")).toEqual([rows[0]]);
  });

  it("matches on a substring", () => {
    expect(filterGenres(rows, "hard")).toHaveLength(2);
  });
});

describe("summarize", () => {
  it("counts each state and the total", () => {
    const counts = summarize([
      row({ id: 1, state: WHITE }),
      row({ id: 2, state: BLACK }),
      row({ id: 3, state: UNKNOWN }),
      row({ id: 4, state: UNKNOWN }),
    ]);
    expect(counts).toEqual({ white: 1, black: 1, unknown: 2, total: 4 });
  });
});

describe("describeOutcome", () => {
  it("describes an approved genre as kept", () => {
    expect(describeOutcome(row({ state: WHITE }))).toBe("Blijft staan");
  });

  it("describes a rejected genre as removed", () => {
    expect(describeOutcome(row({ state: BLACK }))).toBe("Wordt verwijderd");
  });

  it("describes an undecided genre as not saved", () => {
    expect(describeOutcome(row({ state: UNKNOWN }))).toContain("niet opgeslagen");
  });

  it("lets a correction win over the state", () => {
    const corrected = row({
      state: BLACK,
      canonical_targets: [{ id: 9, name: "Uptempo Hardcore" }],
    });
    expect(describeOutcome(corrected)).toBe("Wordt vervangen door Uptempo Hardcore");
  });

  it("names every target of a contraction", () => {
    const contraction = row({
      state: BLACK,
      canonical_targets: [
        { id: 9, name: "Uptempo Hardcore" },
        { id: 10, name: "Terror" },
      ],
    });
    expect(describeOutcome(contraction)).toBe("Wordt vervangen door Uptempo Hardcore + Terror");
  });

  it("treats a missing target list as no correction", () => {
    const withoutTargets = row({ state: WHITE, canonical_targets: undefined });
    expect(describeOutcome(withoutTargets)).toBe("Blijft staan");
  });
});

describe("buildDecision", () => {
  it("builds a payload without a correction", () => {
    expect(buildDecision({ genreId: 1, state: WHITE })).toEqual({
      valid: true,
      error: null,
      payload: { state: WHITE, canonical_ids: [] },
    });
  });

  it("drops empty checkbox values", () => {
    expect(buildDecision({ genreId: 1, state: BLACK, canonicalIds: ["", null] }).payload).toEqual({
      state: BLACK,
      canonical_ids: [],
    });
  });

  it("coerces the checkbox strings to numbers", () => {
    expect(buildDecision({ genreId: 1, state: BLACK, canonicalIds: ["7"] }).payload).toEqual({
      state: BLACK,
      canonical_ids: [7],
    });
  });

  it("keeps several targets, in order, for a contraction", () => {
    expect(buildDecision({ genreId: 1, state: BLACK, canonicalIds: ["7", "9"] }).payload).toEqual({
      state: BLACK,
      canonical_ids: [7, 9],
    });
  });

  it("de-duplicates repeated targets", () => {
    expect(buildDecision({ genreId: 1, state: BLACK, canonicalIds: ["7", 7] }).payload).toEqual({
      state: BLACK,
      canonical_ids: [7],
    });
  });

  it("rejects unknown as a decision, matching the API", () => {
    const decision = buildDecision({ genreId: 1, state: UNKNOWN });
    expect(decision.valid).toBe(false);
    expect(decision.error).toContain("Ongeldige status");
  });

  it("rejects a genre correcting to itself", () => {
    const decision = buildDecision({ genreId: 5, state: BLACK, canonicalIds: ["5"] });
    expect(decision.valid).toBe(false);
    expect(decision.error).toContain("zichzelf");
  });
});

describe("correctionTargets", () => {
  const rows = [
    row({ id: 1, name: "Hardstyle", state: WHITE }),
    row({ id: 2, name: "Arts", state: BLACK }),
    row({ id: 3, name: "Uptempo Hardcore", state: WHITE }),
    row({ id: 4, name: "Unsure", state: UNKNOWN }),
  ];

  it("offers only approved genres", () => {
    expect(correctionTargets(rows, 99).map((r) => r.name)).toEqual([
      "Hardstyle",
      "Uptempo Hardcore",
    ]);
  });

  it("never offers the genre being decided", () => {
    expect(correctionTargets(rows, 1).map((r) => r.name)).toEqual(["Uptempo Hardcore"]);
  });

  it("sorts alphabetically", () => {
    const unsorted = [row({ id: 1, name: "Zzz" }), row({ id: 2, name: "Aaa" })];
    expect(correctionTargets(unsorted, 99).map((r) => r.name)).toEqual(["Aaa", "Zzz"]);
  });
});

describe("describeDecision", () => {
  it("reports an undecided genre", () => {
    expect(describeDecision(row())).toBe("Nog niet beoordeeld");
  });

  it("names who decided", () => {
    const decided = row({ decided_at: "2026-08-01 12:00:00", decided_by: "user" });
    expect(describeDecision(decided)).toContain("door user");
  });
});
