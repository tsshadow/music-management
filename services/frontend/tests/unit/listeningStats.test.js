import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("../../src/lib/mumaApi", () => ({
  apiBase: () => "https://muma.test",
  getHeaders: () => ({ "X-API-Key": "k" }),
}));

import {
  DEFAULT_PERIOD,
  NO_FILTERS,
  UNKNOWN_YEAR,
  byDecade,
  filterParams,
  filtersFromSearch,
  filtersToSearch,
  hasFilters,
  loadGenreOptions,
  setYearBound,
  toggleDecade,
  toggleGenre,
  toggleYear,
  yearSelected,
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
    await loadListening(DEFAULT_PERIOD, NO_FILTERS, fetcher);
    const asked = fetcher.mock.calls.map(([url]) => url);
    for (const path of [
      "summary",
      "timeline",
      "clock",
      "sources",
      "top-tracks",
      "top-artists",
      "top-labels",
      "top-genres",
      "years",
    ]) {
      expect(asked.some((url) => url.includes(`/api/listening/${path}?`))).toBe(true);
    }
  });

  it("reports the bucket it asked for, so the axis can label itself", async () => {
    const data = await loadListening("30d", NO_FILTERS, fetcher);
    expect(data.bucket).toBe("day");
    expect(fetcher.mock.calls.some(([url]) => url.includes("bucket=day"))).toBe(true);
  });

  it("survives a rejected call rather than blanking the page", async () => {
    const failing = vi.fn(async (url) => {
      if (url.includes("top-labels")) throw new Error("nope");
      return { ok: true, json: async () => ({ listens: 1 }) };
    });
    const data = await loadListening("all", NO_FILTERS, failing);
    expect(data.labels).toBeNull();
    expect(data.summary).toEqual({ listens: 1 });
  });

  it("treats a non-2xx answer as missing rather than as data", async () => {
    const data = await loadListening(
      "all",
      NO_FILTERS,
      respondingWith({ detail: "nope" }, { ok: false }),
    );
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

describe("filters in the URL", () => {
  it("reads repeated genres, years, the unknown year and a range", () => {
    const { period, filters } = filtersFromSearch(
      "?period=all&genre=Hardstyle&genre=Uptempo+Hardcore&year=2019&year=unknown&year_from=2010&year_to=2014",
    );
    expect(period).toBe("all");
    expect(filters).toEqual({
      genres: ["Hardstyle", "Uptempo Hardcore"],
      years: [2019],
      unknownYear: true,
      yearFrom: 2010,
      yearTo: 2014,
    });
  });

  it("drops what does not parse rather than sending the server a 400", () => {
    const { period, filters } = filtersFromSearch(
      "period=forever&year=abc&year=12&year_from=x&genre=",
    );
    expect(period).toBe(DEFAULT_PERIOD);
    expect(filters).toEqual(NO_FILTERS);
  });

  it("turns a backwards range round", () => {
    const { filters } = filtersFromSearch("year_from=2020&year_to=2010");
    expect([filters.yearFrom, filters.yearTo]).toEqual([2010, 2020]);
  });

  it("round-trips, so a bookmarked view opens as it was saved", () => {
    const filters = {
      genres: ["Raw Hardstyle"],
      years: [2015, 2019],
      unknownYear: true,
      yearFrom: 2000,
      yearTo: null,
    };
    const search = filtersToSearch("30d", filters);
    expect(filtersFromSearch(search)).toEqual({ period: "30d", filters });
  });

  it("leaves the plain page as the bare path", () => {
    expect(filtersToSearch(DEFAULT_PERIOD, NO_FILTERS)).toBe("");
  });
});

describe("filter toggles", () => {
  it("adds and removes a genre", () => {
    const on = toggleGenre(NO_FILTERS, "Hardcore");
    expect(on.genres).toEqual(["Hardcore"]);
    expect(toggleGenre(on, "Hardcore").genres).toEqual([]);
  });

  it("keeps selected years sorted and toggles the unknown year apart", () => {
    let f = toggleYear(NO_FILTERS, 2019);
    f = toggleYear(f, 2015);
    expect(f.years).toEqual([2015, 2019]);
    f = toggleYear(f, UNKNOWN_YEAR);
    expect(f.unknownYear).toBe(true);
    expect(toggleYear(f, 2019).years).toEqual([2015]);
  });

  it("selects a decade as a range and clears it on a second tap", () => {
    const on = toggleDecade(NO_FILTERS, 2010);
    expect([on.yearFrom, on.yearTo]).toEqual([2010, 2019]);
    expect(toggleDecade(on, 2010).yearFrom).toBeNull();
    expect(toggleDecade(on, 2000).yearTo).toBe(2009);
  });

  it("clears a range end on an empty or implausible input", () => {
    expect(setYearBound(NO_FILTERS, "yearFrom", "2015").yearFrom).toBe(2015);
    expect(setYearBound({ ...NO_FILTERS, yearFrom: 2015 }, "yearFrom", "").yearFrom).toBeNull();
    expect(setYearBound(NO_FILTERS, "yearTo", "99").yearTo).toBeNull();
  });

  it("knows a year selected through the range as well as on its own", () => {
    const f = { ...NO_FILTERS, years: [1999], yearFrom: 2010, yearTo: null };
    expect(yearSelected(f, 1999)).toBe(true);
    expect(yearSelected(f, 2024)).toBe(true);
    expect(yearSelected(f, 2005)).toBe(false);
    expect(yearSelected(NO_FILTERS, 2024)).toBe(false);
  });

  it("says whether anything is filtered", () => {
    expect(hasFilters(NO_FILTERS)).toBe(false);
    expect(hasFilters({ ...NO_FILTERS, unknownYear: true })).toBe(true);
    expect(hasFilters({ ...NO_FILTERS, yearTo: 2000 })).toBe(true);
  });
});

describe("filters sent to the API", () => {
  it("repeats multi-select values in the server's parameter names", () => {
    const params = filterParams({
      genres: ["A", "B"],
      years: [2019],
      unknownYear: true,
      yearFrom: 2010,
      yearTo: 2014,
    });
    expect(params).toEqual({
      genre: ["A", "B"],
      year: ["2019", "unknown"],
      year_from: 2010,
      year_to: 2014,
    });
    const url = listeningUrl("summary", params);
    expect(url).toContain("genre=A&genre=B");
    expect(url).toContain("year=2019&year=unknown");
  });

  it("sends the same filter to every panel", async () => {
    const fetcher = respondingWith({ listens: 1 });
    await loadListening("all", { ...NO_FILTERS, genres: ["Hardcore"] }, fetcher);
    for (const [url] of fetcher.mock.calls) expect(url).toContain("genre=Hardcore");
  });

  it("folds years into decades without double-counting tracks", () => {
    expect(
      byDecade([
        { year: 2011, listens: 3, tracks: 2 },
        { year: 2019, listens: 5, tracks: 1 },
        { year: 1999, listens: 1, tracks: 1 },
      ]),
    ).toEqual([
      { decade: 1990, listens: 1, tracks: 1 },
      { decade: 2010, listens: 8, tracks: 3 },
    ]);
  });

  it("asks for the genre picker's list over the whole history, unfiltered", async () => {
    const fetcher = respondingWith({ genres: [{ genre: "Hardcore" }, { genre: "Hardstyle" }] });
    expect(await loadGenreOptions(fetcher)).toEqual(["Hardcore", "Hardstyle"]);
    const [url] = fetcher.mock.calls[0];
    expect(url).toContain("/api/listening/top-genres?");
    expect(url).not.toContain("from=");
    expect(url).not.toContain("genre=");
  });

  it("gives the picker nothing rather than failing when the call does", async () => {
    expect(
      await loadGenreOptions(
        vi.fn(async () => {
          throw new Error("down");
        }),
      ),
    ).toEqual([]);
  });
});
