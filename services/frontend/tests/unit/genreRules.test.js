import { describe, it, expect } from "vitest";
import {
  RULE_KINDS,
  SECTIONS,
  subjectOf,
  filterRules,
  sortRules,
  countByGenre,
  buildRule,
  describeRule,
  filterOverview,
} from "../../src/lib/management/genreRules";

const ARTIST_RULES = [
  {
    id: 1,
    artist_name: "Angerfist",
    genre_name: "Hardcore",
    genre_id: 72,
    artist_id: 9,
    track_count: 300,
  },
  {
    id: 2,
    artist_name: "Dr. Peacock",
    genre_name: "Frenchcore",
    genre_id: 57,
    artist_id: 10,
    track_count: 816,
  },
  {
    id: 3,
    artist_name: "angerfist",
    genre_name: "Terror",
    genre_id: 145,
    artist_id: null,
    track_count: 0,
  },
];

describe("RULE_KINDS", () => {
  it("names the subject column per kind", () => {
    expect(subjectOf("artist", ARTIST_RULES[0])).toBe("Angerfist");
    expect(subjectOf("label", { label_name: "Roughstate" })).toBe("Roughstate");
    expect(subjectOf("label", undefined)).toBe("");
  });

  it("opens an artist by library id and a label by name, and nothing for an orphan", () => {
    expect(RULE_KINDS.artist.editView(ARTIST_RULES[0])).toBe("artist-edit:9");
    expect(RULE_KINDS.artist.editView(ARTIST_RULES[2])).toBeNull();
    expect(RULE_KINDS.label.editView({ label_name: "Roughstate" })).toBe("label-edit:Roughstate");
  });

  it("lists the page sections queue first", () => {
    expect(SECTIONS.map((s) => s.id)).toEqual(["queue", "overview", "artist-rules", "label-rules"]);
  });
});

describe("filterRules", () => {
  it("matches the subject and the genre, ignoring case and punctuation", () => {
    expect(filterRules("artist", ARTIST_RULES, "dr peacock").map((r) => r.id)).toEqual([2]);
    expect(filterRules("artist", ARTIST_RULES, "FRENCH").map((r) => r.id)).toEqual([2]);
    expect(filterRules("artist", ARTIST_RULES, "anger").map((r) => r.id)).toEqual([1, 3]);
  });

  it("returns everything for an empty query", () => {
    expect(filterRules("artist", ARTIST_RULES, "  ")).toHaveLength(3);
    expect(filterRules("artist", undefined, "x")).toEqual([]);
  });
});

describe("sortRules", () => {
  it("sorts by subject by default, then by genre", () => {
    expect(sortRules("artist", ARTIST_RULES).map((r) => r.id)).toEqual([1, 3, 2]);
  });

  it("sorts by reach with the widest first", () => {
    expect(sortRules("artist", ARTIST_RULES, "tracks").map((r) => r.id)).toEqual([2, 1, 3]);
  });

  it("sorts by genre", () => {
    expect(sortRules("artist", ARTIST_RULES, "genre").map((r) => r.genre_name)).toEqual([
      "Frenchcore",
      "Hardcore",
      "Terror",
    ]);
  });

  it("does not mutate the input", () => {
    const copy = [...ARTIST_RULES];
    sortRules("artist", ARTIST_RULES, "tracks");
    expect(ARTIST_RULES).toEqual(copy);
  });
});

describe("countByGenre", () => {
  it("counts rules per genre id", () => {
    expect(countByGenre(ARTIST_RULES)).toEqual({ 72: 1, 57: 1, 145: 1 });
    expect(countByGenre([])).toEqual({});
  });
});

describe("buildRule", () => {
  it("needs a name and a genre", () => {
    expect(buildRule("artist", { name: " ", genreId: "1" }).error).toBe(
      "management.genres.ruleNeedsName",
    );
    expect(buildRule("artist", { name: "Angerfist", genreId: "" }).error).toBe(
      "management.genres.ruleNeedsGenre",
    );
    expect(buildRule("artist", { name: "Angerfist", genreId: "abc" }).valid).toBe(false);
  });

  it("builds the payload the API takes, per kind", () => {
    expect(buildRule("artist", { name: " Angerfist ", genreId: "72" }).payload).toEqual({
      artist_name: "Angerfist",
      genre_id: 72,
    });
    expect(buildRule("label", { name: "Roughstate", genreId: 72 }).payload).toEqual({
      label_name: "Roughstate",
      genre_id: 72,
    });
  });

  it("refuses a pair that already exists, ignoring case", () => {
    const result = buildRule("artist", {
      name: "ANGERFIST",
      genreId: "72",
      existing: ARTIST_RULES,
    });
    expect(result).toEqual({ valid: false, error: "management.genres.ruleExists" });
    expect(
      buildRule("artist", { name: "Angerfist", genreId: "57", existing: ARTIST_RULES }).valid,
    ).toBe(true);
  });
});

describe("describeRule", () => {
  it("is silent for a seed rule without provenance", () => {
    expect(describeRule({ created_at: null })).toBeNull();
    expect(describeRule(undefined)).toBeNull();
  });

  it("names who and when", () => {
    const described = describeRule({ created_at: "2026-09-18 10:00:00", created_by: "demo-user" });
    expect(described.by).toBe("demo-user");
    expect(described.when).toContain("2026");
  });
});

describe("filterOverview", () => {
  const rows = [
    { id: 1, name: "Industrial Hardcore", parents: ["Hardcore", "Industrial"] },
    { id: 2, name: "Trance", parents: [] },
  ];

  it("matches the name or a parent", () => {
    expect(filterOverview(rows, "indus").map((r) => r.id)).toEqual([1]);
    expect(filterOverview(rows, "hardcore").map((r) => r.id)).toEqual([1]);
    expect(filterOverview(rows, "tran").map((r) => r.id)).toEqual([2]);
    expect(filterOverview(rows, "")).toHaveLength(2);
  });
});
