import { describe, it, expect } from "vitest";
import {
  filterAccounts,
  sortAccounts,
  formatPercent,
  formatAge,
  barSegments,
  reasonLabel,
  stateLabel,
} from "../../src/lib/management/downloaderCoverage";

const NOW = Date.parse("2026-09-21T12:00:00Z");

function row(overrides = {}) {
  return {
    account: "dj_a",
    key: "dj_a",
    listed: 100,
    held: 60,
    excluded: 10,
    remaining: 30,
    coverage: 0.6,
    state: "capped",
    snapshot_at: "2026-09-20T12:00:00Z",
    last_download_at: null,
    ...overrides,
  };
}

const UNCOUNTED = row({
  account: "dj_new",
  key: "dj_new",
  listed: null,
  held: null,
  excluded: null,
  remaining: null,
  coverage: null,
  state: null,
  snapshot_at: null,
});

describe("filterAccounts", () => {
  const rows = [
    row(),
    row({ account: "dj_done", key: "dj_done", remaining: 0, held: 90 }),
    UNCOUNTED,
  ];

  it("keeps only channels with something left by default", () => {
    expect(filterAccounts(rows, "backlog").map((r) => r.account)).toEqual(["dj_a"]);
  });

  it("can show the complete ones and the uncounted ones on their own", () => {
    expect(filterAccounts(rows, "complete").map((r) => r.account)).toEqual(["dj_done"]);
    expect(filterAccounts(rows, "uncounted").map((r) => r.account)).toEqual(["dj_new"]);
  });

  it("searches by name, case-insensitively, within the filter", () => {
    expect(filterAccounts(rows, "all", "DONE").map((r) => r.account)).toEqual(["dj_done"]);
  });

  it("copes with no rows at all", () => {
    expect(filterAccounts(undefined, "backlog")).toEqual([]);
  });
});

describe("sortAccounts", () => {
  const rows = [
    row({
      account: "b",
      key: "b",
      remaining: 5,
      coverage: 0.9,
      last_download_at: "2026-09-01T00:00:00Z",
    }),
    UNCOUNTED,
    row({ account: "a", key: "a", remaining: 50, coverage: 0.2, last_download_at: null }),
    row({
      account: "c",
      key: "c",
      remaining: 5,
      coverage: 0.5,
      last_download_at: "2026-09-19T00:00:00Z",
    }),
  ];

  it("puts the biggest backlog first and breaks ties by name", () => {
    expect(sortAccounts(rows, "remaining").map((r) => r.account)).toEqual([
      "a",
      "b",
      "c",
      "dj_new",
    ]);
  });

  it("can order by lowest coverage", () => {
    expect(sortAccounts(rows, "coverage").map((r) => r.account)).toEqual(["a", "c", "b", "dj_new"]);
  });

  it("can order by newest download, unknown last among the counted", () => {
    expect(sortAccounts(rows, "lastDownload").map((r) => r.account)).toEqual([
      "c",
      "b",
      "a",
      "dj_new",
    ]);
  });

  it("never lets an uncounted channel outrank a counted one", () => {
    expect(sortAccounts(rows, "name").map((r) => r.account)).toEqual(["a", "b", "c", "dj_new"]);
  });
});

describe("formatting", () => {
  it("renders coverage as a whole percentage, or a dash", () => {
    expect(formatPercent(0.3)).toBe("30%");
    expect(formatPercent(0.999)).toBe("100%");
    expect(formatPercent(null)).toBe("—");
  });

  it("renders an age in the coarsest honest unit", () => {
    expect(formatAge("2026-09-21T11:30:00Z", NOW)).toBe("< 1 uur");
    expect(formatAge("2026-09-21T05:00:00Z", NOW)).toBe("7 uur");
    expect(formatAge("2026-09-20T05:00:00Z", NOW)).toBe("1 dag");
    expect(formatAge("2026-09-10T05:00:00Z", NOW)).toBe("11 dagen");
    expect(formatAge("2026-06-10T05:00:00Z", NOW)).toBe("3 mnd");
  });

  it("keeps unknown unknown rather than calling it just now", () => {
    expect(formatAge(null, NOW)).toBeNull();
    expect(formatAge("not a date", NOW)).toBeNull();
  });

  it("splits the bar into held, excluded and remaining that add up to 100", () => {
    const bar = barSegments(row());
    expect(bar).toEqual({ held: 60, excluded: 10, remaining: 30 });
  });

  it("leaves the bar empty for an uncounted channel", () => {
    expect(barSegments(UNCOUNTED)).toEqual({ held: 0, excluded: 0, remaining: 0 });
  });

  it("names the write-off reasons and pass states in Dutch, unknown ones verbatim", () => {
    expect(reasonLabel("too_short")).toBe("te kort");
    expect(reasonLabel("quarantined")).toBe("quarantined");
    expect(stateLabel("parked")).toBe("onderbroken");
    expect(stateLabel(null)).toBe("nog niet geteld");
  });
});
