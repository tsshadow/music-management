import { describe, expect, it } from "vitest";

import {
  catid,
  formatRun,
  formatRuns,
  searchTerms,
  seriesHeader,
} from "../../src/lib/curation/catalogRuns";

const DWX = { prefix: "DWX", separator: "", width: 4, absent_runs: [] };

describe("catid", () => {
  it("pads to the series' width", () => {
    expect(catid(DWX, 177)).toBe("DWX0177");
  });

  it("never truncates a number wider than the width", () => {
    expect(catid({ ...DWX, width: 3 }, 2212)).toBe("DWX2212");
  });

  it("writes the separator the series uses", () => {
    expect(catid({ prefix: "R909", separator: "-", width: 2 }, 30)).toBe("R909-30");
  });

  it("writes a bare number for a series without a prefix", () => {
    expect(catid({ prefix: "", width: 3 }, 7)).toBe("007");
  });
});

describe("formatRun", () => {
  it("shows a lone number as itself", () => {
    expect(formatRun(DWX, [177, 177])).toBe("DWX0177");
  });

  it("shows a stretch with an en dash", () => {
    expect(formatRun(DWX, [287, 289])).toBe("DWX0287–DWX0289");
  });
});

describe("formatRuns", () => {
  it("joins the runs with commas", () => {
    const series = {
      ...DWX,
      absent_runs: [
        [177, 177],
        [223, 223],
        [287, 289],
      ],
    };
    expect(formatRuns(series)).toBe("DWX0177, DWX0223, DWX0287–DWX0289");
  });

  it("formats a slice when asked, so the section can fold the tail", () => {
    const series = {
      ...DWX,
      absent_runs: [
        [1, 1],
        [3, 3],
        [5, 5],
      ],
    };
    expect(formatRuns(series, series.absent_runs.slice(0, 2))).toBe("DWX0001, DWX0003");
  });
});

describe("searchTerms", () => {
  it("expands every run to one fully written number per line", () => {
    const series = {
      ...DWX,
      absent_runs: [
        [177, 177],
        [287, 289],
      ],
    };
    expect(searchTerms(series)).toBe("DWX0177\nDWX0287\nDWX0288\nDWX0289");
  });

  it("is empty when nothing is absent", () => {
    expect(searchTerms(DWX)).toBe("");
  });
});

describe("seriesHeader", () => {
  it("names the series, its padded range and the share present", () => {
    const series = { ...DWX, min: 0, max: 2212, present: 1921, coverage: 0.868 };
    expect(seriesHeader(series)).toBe("DWX · 0000–2212 · 1921 van 2213 aanwezig (87%)");
  });

  it("names a series without a prefix", () => {
    const series = { prefix: "", width: 3, min: 0, max: 9, present: 10, coverage: 1 };
    expect(seriesHeader(series)).toBe("(geen prefix) · 000–009 · 10 van 10 aanwezig (100%)");
  });
});
