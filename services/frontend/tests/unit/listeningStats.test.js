import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../../src/lib/mumaApi", () => ({
  apiBase: () => "https://muma.test",
  getHeaders: () => ({ "X-API-Key": "k" }),
}));

import {
  DEFAULT_PERIOD,
  bucketFor,
  bucketLabel,
  browserTimeZone,
  listeningUrl,
  loadListening,
  measuredPercent,
  peak,
  periodRange,
  splitDuration,
  unmatchedPercent,
} from "../../src/lib/listeningStats.js";

/** A fetch stub answering every endpoint with the same body. */
function respondingWith(body, { ok = true } = {}) {
  return vi.fn(async () => ({ ok, json: async () => body }));
}

describe("periodRange", () => {
  it("leaves the range open for all time, so the server reads the whole history", () => {
    expect(periodRange("all")).toEqual({});
  });

  it("counts a period back from today in the browser's own calendar", () => {
    const range = periodRange("30d", new Date(2026, 8, 6));
    expect(range).toEqual({ from: "2026-08-07", to: "2026-09-06" });
  });

  it("pads a single-digit month and day, which the API parses as ISO dates", () => {
    expect(periodRange("30d", new Date(2026, 1, 3)).to).toBe("2026-02-03");
  });

  it("treats an unknown period as no range rather than throwing", () => {
    expect(periodRange("since-forever")).toEqual({});
  });
});

describe("bucketFor", () => {
  it.each([
    ["30d", "day"],
    ["12m", "week"],
    ["all", "month"],
  ])("draws %s in %s buckets", (period, bucket) => {
    expect(bucketFor(period)).toBe(bucket);
  });

  it("never asks for three years of daily bars", () => {
    expect(bucketFor("all")).not.toBe("day");
  });
});

describe("listeningUrl", () => {
  it("always names a timezone, because the server stores listens in UTC", () => {
    expect(listeningUrl("clock")).toContain(`tz=${encodeURIComponent(browserTimeZone())}`);
  });

  it("drops empty parameters instead of sending them blank", () => {
    const url = listeningUrl("summary", { from: "", to: undefined, limit: 10 });
    expect(url).not.toContain("from=");
    expect(url).not.toContain("to=");
    expect(url).toContain("limit=10");
  });

  it("hangs off the configured API base", () => {
    expect(listeningUrl("summary")).toContain("https://muma.test/api/listening/summary?");
  });
});

describe("loadListening", () => {
  let fetcher;

  beforeEach(() => {
    fetcher = respondingWith({ listens: 1 });
  });

  it("asks for every panel of the page", async () => {
    await loadListening(DEFAULT_PERIOD, fetcher);
    const asked = fetcher.mock.calls.map(([url]) => url);
    for (const path of [
      "summary",
      "timeline",
      "clock",
      "sources",
      "top-tracks",
      "top-artists",
      "top-labels",
    ]) {
      expect(asked.some((url) => url.includes(`/api/listening/${path}?`))).toBe(true);
    }
  });

  it("reports the bucket it asked for, so the axis can label itself", async () => {
    const data = await loadListening("30d", fetcher);
    expect(data.bucket).toBe("day");
    expect(fetcher.mock.calls.some(([url]) => url.includes("bucket=day"))).toBe(true);
  });

  it("survives a rejected call rather than blanking the page", async () => {
    const failing = vi.fn(async (url) => {
      if (url.includes("top-labels")) throw new Error("nope");
      return { ok: true, json: async () => ({ listens: 1 }) };
    });
    const data = await loadListening("all", failing);
    expect(data.labels).toBeNull();
    expect(data.summary).toEqual({ listens: 1 });
  });

  it("treats a non-2xx answer as missing rather than as data", async () => {
    const data = await loadListening("all", respondingWith({ detail: "nope" }, { ok: false }));
    expect(data.summary).toBeNull();
  });
});

describe("peak", () => {
  it("never returns zero, so a bar height cannot divide by nothing", () => {
    expect(peak([])).toBe(1);
    expect(peak([{ listens: 0 }, { listens: 0 }])).toBe(1);
  });

  it("reads the largest value of the named field", () => {
    expect(peak([{ listens: 3 }, { listens: 11 }, { listens: 7 }])).toBe(11);
  });
});

describe("splitDuration", () => {
  it("splits seconds into whole hours and the minutes left over", () => {
    expect(splitDuration(3600 * 653 + 60 * 42)).toEqual({ hours: 653, minutes: 42 });
  });

  it("reads nothing as zero rather than NaN", () => {
    expect(splitDuration(undefined)).toEqual({ hours: 0, minutes: 0 });
  });
});

describe("the disclosures the page is obliged to make", () => {
  it("states what share of the history could not be ranked", () => {
    expect(unmatchedPercent({ listens: 53760, unmatched: 33461 })).toBe(62);
  });

  it("states what share of the listening time was measured rather than assumed", () => {
    expect(measuredPercent({ listens: 20299, measured_listens: 876 })).toBe(4);
  });

  it("says nothing rather than 0% when there is no history at all", () => {
    expect(unmatchedPercent({ listens: 0, unmatched: 0 })).toBeNull();
    expect(measuredPercent(null)).toBeNull();
  });
});

describe("bucketLabel", () => {
  it.each([
    ["2026-09-06", "day", "06/09"],
    ["2026-W37", "week", "w37"],
    ["2026-09", "month", "09/26"],
  ])("shortens %s for an axis", (key, bucket, expected) => {
    expect(bucketLabel(key, bucket)).toBe(expected);
  });

  it("returns nothing for a missing bucket", () => {
    expect(bucketLabel(undefined, "day")).toBe("");
  });
});
