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
  describeProposal,
  decisionFromProposal,
  planFromProposals,
  BULK_CONFIDENCE_FLOOR,
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

describe("describeProposal", () => {
  const proposalRow = (proposal) =>
    row({ id: 7, name: "Frenchcore/Terror", state: UNKNOWN, proposal });

  it("is silent without a proposal", () => {
    expect(describeProposal(row({ proposal: null }))).toBeNull();
    expect(
      describeProposal(row({ proposal: { kind: "unknown", targets: [], confidence: 0 } })),
    ).toBeNull();
  });

  it("names every target of a split", () => {
    const described = describeProposal(
      proposalRow({
        kind: "split",
        targets: [
          { id: 1, name: "Frenchcore" },
          { id: 2, name: "Terror" },
        ],
        confidence: 90,
      }),
    );
    expect(described).toEqual({
      key: "management.genres.proposeRewrite",
      vars: { target: "Frenchcore + Terror" },
    });
  });

  it("describes a rejection and a keep", () => {
    expect(describeProposal(proposalRow({ kind: "reject", targets: [] })).key).toBe(
      "management.genres.proposeReject",
    );
    expect(describeProposal(proposalRow({ kind: "keep", targets: [] })).key).toBe(
      "management.genres.proposeKeep",
    );
  });

  it("has nothing to say about a rewrite whose targets went missing", () => {
    expect(describeProposal(proposalRow({ kind: "rewrite", targets: [] }))).toBeNull();
  });
});

describe("decisionFromProposal", () => {
  it("turns a split into a rejection with the targets, as the dialog would", () => {
    const decision = decisionFromProposal(
      row({
        id: 7,
        proposal: {
          kind: "split",
          targets: [
            { id: "3", name: "Uptempo Hardcore" },
            { id: 2, name: "Terror" },
          ],
        },
      }),
    );
    expect(decision).toEqual({ genreId: 7, state: BLACK, canonicalIds: [3, 2] });
    expect(buildDecision(decision).valid).toBe(true);
  });

  it("turns a rejection into a plain rejection and a keep into an approval", () => {
    expect(decisionFromProposal(row({ id: 7, proposal: { kind: "reject", targets: [] } }))).toEqual(
      {
        genreId: 7,
        state: BLACK,
        canonicalIds: [],
      },
    );
    expect(
      decisionFromProposal(row({ id: 7, proposal: { kind: "keep", targets: [] } })).state,
    ).toBe(WHITE);
  });

  it("has nothing to apply for unknown advice or no advice", () => {
    expect(decisionFromProposal(row({ proposal: { kind: "unknown", targets: [] } }))).toBeNull();
    expect(decisionFromProposal(row({ proposal: null }))).toBeNull();
    expect(decisionFromProposal(row({ proposal: { kind: "rewrite", targets: [] } }))).toBeNull();
  });
});

describe("planFromProposals", () => {
  const rows = [
    row({
      id: 1,
      proposal: { kind: "split", targets: [{ id: 9, name: "Terror" }], confidence: 90 },
    }),
    row({ id: 2, proposal: { kind: "reject", targets: [], confidence: 50 } }),
    row({ id: 3, proposal: { kind: "unknown", targets: [], confidence: 0 } }),
    row({ id: 4, proposal: null }),
    row({ id: 5, proposal: { kind: "reject", targets: [], confidence: 85 } }),
  ];

  it("applies confident advice and leaves hunches alone", () => {
    const plan = planFromProposals(rows);
    expect(plan.applicable.map((r) => r.id)).toEqual([1, 5]);
    expect(plan.skipped.map((r) => r.id)).toEqual([2, 3, 4]);
  });

  it("takes a different floor", () => {
    expect(planFromProposals(rows, 0).applicable.map((r) => r.id)).toEqual([1, 2, 5]);
    expect(BULK_CONFIDENCE_FLOOR).toBe(60);
  });

  it("copes with no rows", () => {
    expect(planFromProposals(undefined)).toEqual({ applicable: [], skipped: [] });
  });
});
