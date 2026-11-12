import { describe, it, expect, vi } from "vitest";
import en from "../../src/lib/i18n/locales/en.json";
import nl from "../../src/lib/i18n/locales/nl.json";
import { createTranslator } from "../../src/lib/i18n/index.js";
import {
  CARD_KINDS,
  barPercent,
  describeCard,
  describeCoverage,
  durationText,
  formatters,
  hasListens,
  homeTileYear,
  leadingGenre,
  loadPeriods,
  loadTab,
  parsePeriodKey,
  parseWrappedRoute,
  periodLabel,
  periodParams,
  pickerYears,
  playablePaths,
  rangeKey,
  retryAfterMs,
  visibleCards,
  wrappedUrl,
  wrappedView,
} from "../../src/lib/wrapped/wrapped.js";
import { ALL_CARDS, payloadWith } from "./wrappedFixture.js";

const tEn = createTranslator({ en }, "en");
const tNl = createTranslator({ en, nl }, "nl");
const f = formatters(tEn, "en");

/** A fetch answer. */
function answer(status, body, headers = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name) => headers[name] ?? null },
    json: async () => body,
  };
}

describe("period keys and routes", () => {
  it("reads a year and a range, and refuses anything else", () => {
    expect(parsePeriodKey("2026")).toEqual({ key: "2026", year: 2026 });
    expect(parsePeriodKey("2026-03-01_2026-06-30")).toEqual({
      key: "2026-03-01_2026-06-30",
      from: "2026-03-01",
      to: "2026-06-30",
    });
    expect(parsePeriodKey("2026-06-30_2026-03-01")).toBeNull();
    expect(parsePeriodKey("last-year")).toBeNull();
    expect(parsePeriodKey(undefined)).toBeNull();
  });

  it("builds a range key only for two ordered dates at most three years apart", () => {
    expect(rangeKey("2025-01-01", "2025-12-31")).toBe("2025-01-01_2025-12-31");
    expect(rangeKey("2025-01-01", "2025-01-01")).toBe("2025-01-01_2025-01-01");
    expect(rangeKey("2020-01-01", "2025-01-01")).toBeNull();
    expect(rangeKey("", "2025-01-01")).toBeNull();
    expect(rangeKey("2025-13-45", "2025-14-01")).toBeNull();
  });

  it("lands a stale or bare route on the running year's user tab", () => {
    const now = new Date(2026, 10, 12);
    expect(parseWrappedRoute("", now)).toEqual({ periodKey: "2026", tab: "user" });
    expect(parseWrappedRoute("nonsense/other", now)).toEqual({ periodKey: "2026", tab: "user" });
    expect(parseWrappedRoute("2024/library", now)).toEqual({ periodKey: "2024", tab: "library" });
    expect(wrappedView("2024", "library")).toBe("wrapped:2024/library");
  });

  it("sends the browser zone for the user tab only", () => {
    expect(periodParams("2026")).toEqual({ year: "2026" });
    expect(periodParams("2026-03-01_2026-06-30")).toEqual({ from: "2026-03-01", to: "2026-06-30" });
    expect(periodParams("bad")).toEqual({});
    expect(wrappedUrl("user", "2026", "Europe/Amsterdam")).toContain(
      "/api/wrapped/user?year=2026&tz=Europe%2FAmsterdam",
    );
    expect(wrappedUrl("library", "2026", "Europe/Amsterdam")).toMatch(
      /\/api\/wrapped\/library\?year=2026$/,
    );
  });

  it("offers a home tile in December and January only", () => {
    expect(homeTileYear(new Date(2026, 11, 1))).toBe(2026);
    expect(homeTileYear(new Date(2027, 0, 31))).toBe(2026);
    expect(homeTileYear(new Date(2026, 10, 30))).toBeNull();
    expect(homeTileYear(new Date(2027, 1, 1))).toBeNull();
  });

  it("lists the server's years plus the year on screen, newest first", () => {
    expect(pickerYears([{ year: 2024 }, { year: 2025 }], "2026")).toEqual([2026, 2025, 2024]);
    expect(pickerYears([], "2026-01-01_2026-02-01")).toEqual([]);
    expect(pickerYears(null, "2025")).toEqual([2025]);
  });
});

describe("loading", () => {
  it("returns the years, or nothing when the server cannot be asked", async () => {
    const years = [{ year: 2026, listens: 5, own_listens: 5 }];
    expect(await loadPeriods(vi.fn(async () => answer(200, { years, server_tz: "UTC" })))).toEqual(
      years,
    );
    expect(await loadPeriods(vi.fn(async () => answer(500, {})))).toEqual([]);
    expect(await loadPeriods(vi.fn(async () => answer(200, {})))).toEqual([]);
    expect(await loadPeriods(vi.fn(async () => Promise.reject(new Error("offline"))))).toEqual([]);
  });

  it("waits once for a tab the server is still computing", async () => {
    const payload = payloadWith([]);
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(answer(503, {}, { "Retry-After": "5" }))
      .mockResolvedValueOnce(answer(200, payload));
    const wait = vi.fn(async () => {});
    const onComputing = vi.fn();
    const result = await loadTab("user", "2026", { fetcher, wait, onComputing });
    expect(result).toEqual({ state: "ok", payload });
    expect(onComputing).toHaveBeenCalledOnce();
    expect(wait).toHaveBeenCalledWith(5000);
  });

  it("gives up after a second 503, another error, a network failure or a bad body", async () => {
    const wait = vi.fn(async () => {});
    const busy = vi.fn(async () => answer(503, {}));
    expect(await loadTab("user", "2026", { fetcher: busy, wait })).toEqual({
      state: "unavailable",
    });
    expect(busy).toHaveBeenCalledTimes(2);
    expect(await loadTab("user", "2026", { fetcher: async () => answer(500, {}), wait })).toEqual({
      state: "unavailable",
    });
    expect(
      await loadTab("user", "2026", { fetcher: async () => Promise.reject(new Error("x")), wait }),
    ).toEqual({
      state: "unavailable",
    });
    const badBody = { ok: true, status: 200, json: async () => Promise.reject(new Error("bad")) };
    expect(await loadTab("library", "2026", { fetcher: async () => badBody, wait })).toEqual({
      state: "unavailable",
    });
  });

  it("caps the Retry-After wait at a minute and defaults to 20 seconds", () => {
    expect(retryAfterMs(answer(503, {}, { "Retry-After": "20" }))).toBe(20000);
    expect(retryAfterMs(answer(503, {}, { "Retry-After": "600" }))).toBe(60000);
    expect(retryAfterMs(answer(503, {}))).toBe(20000);
    expect(retryAfterMs({})).toBe(20000);
  });
});

describe("cards", () => {
  it("draws only ok cards of a known kind, in the server's order", () => {
    const payload = payloadWith([
      ALL_CARDS[0],
      { id: "streak", status: "below_minimum", reason: null, basis: null, data: null },
      { id: "mystery", status: "ok", reason: null, basis: null, data: {} },
      ALL_CARDS[3],
    ]);
    expect(visibleCards(payload).map((card) => card.id)).toEqual(["title", "top_tracks"]);
    expect(visibleCards(null)).toEqual([]);
  });

  it("knows every card the fixture sends", () => {
    for (const card of ALL_CARDS) expect(CARD_KINDS[card.id]).toBeTruthy();
  });

  it("builds a face with a label, headline and sentence for every card in both languages", () => {
    const fNl = formatters(tNl, "nl");
    for (const card of ALL_CARDS) {
      for (const [fmt, scope] of [
        [f, "user"],
        [fNl, "library"],
      ]) {
        const face = describeCard(card, fmt, { scope, period: "2026" });
        expect(face.kind).toBe(CARD_KINDS[card.id]);
        expect(face.label, card.id).not.toMatch(/^wrapped\./);
        expect(face.sentence, card.id).not.toMatch(/^wrapped\./);
        expect(face.sentence, card.id).not.toMatch(/\{\w+\}/);
        expect(face.headline, card.id).not.toBe("");
        for (const note of face.notes) expect(note, card.id).not.toMatch(/\{\w+\}|^wrapped\./);
      }
    }
  });

  it("says how many listens a card could not count, and what it was based on", () => {
    const face = describeCard(
      ALL_CARDS.find((card) => card.id === "top_tracks"),
      f,
    );
    expect(face.headline).toBe("Track One");
    expect(face.sentence).toBe("by Artist A, played 50 times.");
    expect(face.notes).toEqual([
      "3,000 listens could not be matched to a track and are not counted here.",
      "Based on 9,000 of 12,000 listens.",
    ]);
    expect(face.items).toHaveLength(3);
    expect(face.playable).toBe(true);
  });

  it("writes the title card per tab", () => {
    const title = ALL_CARDS[0];
    expect(describeCard(title, f, { scope: "user", period: "2026" }).label).toBe("Your 2026");
    const library = describeCard(title, f, { scope: "library", period: "2026" });
    expect(library.label).toBe("The library's 2026");
    expect(library.sentence).toContain("4 listeners");
    expect(library.notes).toEqual([]);
  });

  it("picks the right wording for optional parts", () => {
    const byId = (id) => ALL_CARDS.find((card) => card.id === id);
    expect(describeCard(byId("origins"), f).sentence).toContain("in the car");
    const noCar = { ...byId("origins"), data: { ...byId("origins").data, car_secs: 0 } };
    expect(describeCard(noCar, f).sentence).toBe("Your most used device.");
    const noTrack = { ...byId("only_you"), data: { ...byId("only_you").data, track: null } };
    expect(describeCard(noTrack, f).headline).toBe("300");
    const noChannel = {
      ...byId("downloads"),
      data: { ...byId("downloads").data, top_channel: null, undated: 0 },
    };
    expect(describeCard(noChannel, f).sentence).toBe("Downloads per month.");
    expect(describeCard(noChannel, f).notes).toEqual([]);
    expect(describeCard(byId("ratings"), f).notes[0]).toMatch(/rebuilt/);
    expect(describeCard(byId("clock"), f).headline).toBe("22:00");
    expect(describeCard(byId("heatmap"), f).headline).toBe("Saturday 23:00");
    expect(describeCard(byId("taste_vs_shelf"), f).series).toEqual(["You", "Library"]);
  });

  it("links artists, genres, labels and festivals to their pages", () => {
    const byId = (id) =>
      describeCard(
        ALL_CARDS.find((card) => card.id === id),
        f,
      );
    expect(byId("top_artists").items[0].link).toEqual({ type: "artist", name: "Artist A" });
    expect(byId("top_genres").items[0].link).toEqual({ type: "genre", name: "Hardcore" });
    expect(byId("top_label").items[1].link).toEqual({ type: "label", name: "Label Y" });
    expect(byId("festival").items[0].link).toEqual({ type: "festival", name: "Fest F" });
    expect(byId("discovery").link).toEqual({ type: "artist", name: "Artist D" });
  });

  it("tints a genre card by its leading genre", () => {
    expect(leadingGenre(ALL_CARDS.find((card) => card.id === "top_genres"))).toBe("Hardcore");
    expect(leadingGenre(ALL_CARDS.find((card) => card.id === "seasons"))).toBe("Hardcore");
    expect(leadingGenre(ALL_CARDS.find((card) => card.id === "new_genres"))).toBe("Frenchcore");
    expect(leadingGenre(ALL_CARDS[0])).toBeNull();
  });

  it("plays the library paths of a track card", () => {
    expect(playablePaths(ALL_CARDS.find((card) => card.id === "top_tracks"))).toEqual([
      "Labels/Track One.flac",
      "Labels/Track Two.flac",
      "Labels/Track Three.flac",
    ]);
    expect(playablePaths(ALL_CARDS[0])).toEqual([]);
  });

  it("describes the coverage and every card left out", () => {
    const model = describeCoverage(payloadWith([]).coverage, f);
    expect(model.sentence).toContain("12,000 listens");
    expect(model.shares.map((share) => share.value)).toEqual(["4%", "80%", "70%", "50%"]);
    expect(model.leftOut).toEqual([
      { id: "top_remixer", label: "Top remixer", reason: "No track has a remixer credit." },
      { id: "streak", label: "Longest streak", reason: "Too little data for this period." },
    ]);
    expect(describeCoverage(null, f).leftOut).toEqual([]);
  });

  it("knows whether a tab has listens", () => {
    expect(hasListens(payloadWith([]))).toBe(true);
    expect(hasListens({ coverage: { listens: 0 } })).toBe(false);
    expect(hasListens(null)).toBe(false);
  });
});

describe("formatting", () => {
  it("picks the unit that reads best", () => {
    expect(durationText(1800, tEn)).toBe("30 minutes");
    expect(durationText(7200, tEn)).toBe("2 hours");
    expect(durationText(3 * 86400, tEn)).toBe("3 days");
    expect(durationText(3 * 365.25 * 86400, tEn)).toBe("3 years");
    expect(durationText(60, tEn)).toBe("1 minute");
    expect(durationText(undefined, tEn)).toBe("0 minutes");
  });

  it("labels a running year, a closed year and a range", () => {
    expect(periodLabel({ year: 2026, running: true }, f)).toBe("2026 so far");
    expect(periodLabel({ year: 2025, running: false }, f)).toBe("2025");
    expect(periodLabel({ year: null, from: "2026-03-01", to: "2026-06-30" }, f)).toMatch(/ to /);
    expect(periodLabel(null, f)).toBe("");
  });

  it("formats months, percentages and tempos", () => {
    expect(f.month("2026-03")).toBe("Mar");
    expect(f.month("bad")).toBe("bad");
    expect(f.percent(0.1234)).toBe("12.3%");
    expect(f.bpm(162.44)).toBe("162.4 BPM");
    expect(f.date("")).toBe("");
    expect(f.dateTime(null)).toBe("");
  });

  it("scales a bar against the peak", () => {
    expect(barPercent(5, 10)).toBe(50);
    expect(barPercent(20, 10)).toBe(100);
    expect(barPercent(5, 0)).toBe(0);
  });
});
