import { describe, it, expect } from "vitest";
import {
  AUTO_DECIDER,
  BLACK,
  UNKNOWN,
  WHITE,
  listParams,
  buildDecision,
  describeOutcome,
  describeProposal,
  describeDecision,
  pageOf,
  planFromProposals,
} from "../../src/lib/management/artistCuration.js";

describe("buildDecision", () => {
  it("trims, deduplicates and drops empty names", () => {
    const decision = buildDecision({ names: [" Premiere ", "Premiere", "", null], state: BLACK });
    expect(decision.valid).toBe(true);
    expect(decision.payload).toEqual({ names: ["Premiere"], state: BLACK, canonical_name: null });
  });

  it("refuses an empty selection and an unknown state", () => {
    expect(buildDecision({ names: [], state: BLACK }).valid).toBe(false);
    expect(buildDecision({ names: ["x"], state: "grey" }).valid).toBe(false);
  });

  it("an approval cannot carry a correction", () => {
    const decision = buildDecision({
      names: ["Angerfist"],
      state: WHITE,
      canonicalName: "Angerfist!",
    });
    expect(decision.valid).toBe(false);
    expect(decision.error).toBe("management.artists.errorApproveWithCorrection");
  });

  it("a name cannot correct to itself, whatever the casing", () => {
    const decision = buildDecision({
      names: ["Angerfist"],
      state: BLACK,
      canonicalName: "angerfist",
    });
    expect(decision.valid).toBe(false);
    expect(decision.error).toBe("management.artists.errorSelfCorrection");
  });

  it("carries the correction on a rejection", () => {
    const decision = buildDecision({
      names: ["Dr.Peacock"],
      state: BLACK,
      canonicalName: " Dr. Peacock ",
    });
    expect(decision.payload.canonical_name).toBe("Dr. Peacock");
  });
});

describe("planFromProposals", () => {
  it("turns rejects into one call and rewrites into one call per target", () => {
    const plan = planFromProposals([
      { name: "Premiere", proposal_kind: "reject" },
      { name: "OUT NOW", proposal_kind: "reject" },
      { name: "Dr.Peacock", proposal_kind: "rewrite", proposal_target: "Dr. Peacock" },
      { name: "dr peacock", proposal_kind: "rewrite", proposal_target: "Dr. Peacock" },
      { name: "DJ Angerfist", proposal_kind: "rewrite", proposal_target: "Angerfist" },
      { name: "Boaz Van De Beatz", proposal_kind: "unknown" },
      { name: "Nobody", proposal_kind: null },
    ]);
    expect(plan.decisions).toEqual([
      { names: ["Premiere", "OUT NOW"], state: BLACK, canonical_name: null },
      { names: ["Dr.Peacock", "dr peacock"], state: BLACK, canonical_name: "Dr. Peacock" },
      { names: ["DJ Angerfist"], state: BLACK, canonical_name: "Angerfist" },
    ]);
    expect(plan.skipped).toEqual(["Boaz Van De Beatz", "Nobody"]);
  });

  it("is empty for no rows", () => {
    expect(planFromProposals([])).toEqual({ decisions: [], skipped: [] });
  });
});

describe("describing a row", () => {
  it("a correction wins over the state", () => {
    expect(describeOutcome({ state: BLACK, canonical_name: "Angerfist" })).toEqual({
      key: "management.artists.outcomeRewrite",
      vars: { target: "Angerfist" },
    });
    expect(describeOutcome({ state: BLACK }).key).toBe("management.artists.outcomeDrop");
    expect(describeOutcome({ state: WHITE }).key).toBe("management.artists.outcomeKeep");
    expect(describeOutcome({ state: "unknown" }).key).toBe("management.artists.outcomeUndecided");
  });

  it("says what the analysis advised, or nothing", () => {
    expect(describeProposal({ proposal_kind: "reject" }).key).toBe(
      "management.artists.proposeReject",
    );
    expect(describeProposal({ proposal_kind: "rewrite", proposal_target: "Angerfist" })).toEqual({
      key: "management.artists.proposeRewrite",
      vars: { target: "Angerfist" },
    });
    expect(describeProposal({ proposal_kind: "unknown" })).toBeNull();
    expect(describeProposal({})).toBeNull();
  });

  it("names who decided and when", () => {
    expect(describeDecision({})).toBeNull();
    const decision = describeDecision({ decided_at: "2026-09-16 04:00:00", decided_by: "user" });
    expect(decision.by).toBe("user");
    expect(decision.when).toContain("2026");
  });
});

describe("pageOf", () => {
  it("counts pages from the total and the offset", () => {
    expect(pageOf(0, 0)).toEqual({ page: 1, pages: 1 });
    expect(pageOf(250, 0)).toEqual({ page: 1, pages: 3 });
    expect(pageOf(250, 200)).toEqual({ page: 3, pages: 3 });
    expect(pageOf(250, 900)).toEqual({ page: 3, pages: 3 });
  });
});

describe("listParams", () => {
  it("asks for one page of a state, with the search trimmed", () => {
    const params = listParams({ state: UNKNOWN, offset: 200, search: "  peac " });
    expect(Object.fromEntries(params)).toEqual({
      state: "unknown",
      limit: "100",
      offset: "200",
      q: "peac",
    });
  });

  it("sends the advice filter only for the queue", () => {
    expect(listParams({ state: UNKNOWN, offset: 0, proposal: "reject" }).get("proposal")).toBe(
      "reject",
    );
    expect(listParams({ state: WHITE, offset: 0, proposal: "reject" }).has("proposal")).toBe(false);
  });

  it("turns the automatic filter into the evidence run's review list, newest decision first", () => {
    const params = listParams({ state: WHITE, offset: 0, decider: AUTO_DECIDER });
    expect(params.get("decided_by")).toBe("auto-external");
    expect(params.get("sort")).toBe("decided");
    expect(listParams({ state: BLACK, offset: 0, decider: AUTO_DECIDER }).has("decided_by")).toBe(
      false,
    );
  });
});
