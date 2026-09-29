import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import ListeningStatsView from "../../src/lib/ListeningStatsView.svelte";

const SUMMARY = {
  listens: 53760,
  matched: 20299,
  unmatched: 33461,
  unmatched_share: 0.6224,
  tracks: 3319,
  artists: 812,
  measured_listens: 876,
  imputed_listens: 19423,
  unknown_duration_listens: 33461,
  measured_share: 0.0163,
  measured_secs: 120000,
  imputed_secs: 2230800,
  estimated_secs: 2350800,
  first_listen: "2024-03-28T05:36:44",
  last_listen: "2026-09-06T12:00:00",
};

const BODIES = {
  summary: SUMMARY,
  timeline: {
    bucket: "week",
    timezone: "Europe/Amsterdam",
    buckets: [
      { bucket: "2026-W36", matched: 40, unmatched: 60, listens: 100 },
      { bucket: "2026-W37", matched: 70, unmatched: 10, listens: 80 },
    ],
  },
  clock: {
    timezone: "Europe/Amsterdam",
    hours: Array.from({ length: 24 }, (_, hour) => (hour === 22 ? 900 : hour)),
    weekdays: [10, 20, 30, 40, 50, 60, 70],
  },
  sources: {
    sources: [
      { source: "listenbrainz_import", matched: 11993, unmatched: 20000, listens: 31993 },
      { source: "mobile", matched: 414, unmatched: 0, listens: 414 },
    ],
  },
  "top-tracks": {
    unmatched: 33461,
    tracks: [
      {
        track_id: 1,
        title: "Raise Your Fist",
        artist: "Angerfist",
        listens: 42,
        estimated_secs: 9000,
        last_listen: "2026-09-05T20:00:00",
      },
      {
        track_id: 2,
        title: "Nameless",
        artist: null,
        listens: 12,
        estimated_secs: 2400,
        last_listen: null,
      },
    ],
  },
  "top-artists": {
    unmatched: 33461,
    artists: [
      { artist_id: 7, artist: "Nosferatu", listens: 130, tracks: 21, estimated_secs: 30000 },
    ],
  },
  "top-labels": {
    unmatched: 33461,
    labels: [{ label_id: 3, label: "Peacock Records", listens: 220, tracks: 40 }],
  },
  "top-genres": {
    unmatched: 33461,
    excluded_unmatched: 0,
    matched: 20299,
    untagged: 7000,
    genres: [
      { genre_id: 1, genre: "Hardcore", listens: 9294, tracks: 3250 },
      { genre_id: 2, genre: "Uptempo Hardcore", listens: 7479, tracks: 2223 },
    ],
  },
  years: {
    unmatched: 33461,
    excluded_unmatched: 0,
    matched: 20299,
    unknown: { listens: 5000, tracks: 900 },
    years: [
      { year: 2015, listens: 7000, tracks: 1000 },
      { year: 2019, listens: 8299, tracks: 1200 },
    ],
  },
};

/** Answers each /api/listening call with the body belonging to its path. */
function listeningApi(overrides = {}) {
  const bodies = { ...BODIES, ...overrides };
  return vi.fn(async (url) => {
    const path = String(url).split("/api/listening/")[1]?.split("?")[0];
    const body = bodies[path];
    if (body === undefined) return { ok: false, json: async () => ({}) };
    return { ok: true, json: async () => body };
  });
}

/** The query string of every /api/listening call made so far, for one endpoint. */
function callsTo(path) {
  return globalThis.fetch.mock.calls
    .map(([url]) => String(url))
    .filter((url) => url.includes(`/api/listening/${path}?`));
}

describe("ListeningStatsView", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/listening");
    globalThis.fetch = listeningApi();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("shows the totals over both matched and unmatched listens", async () => {
    render(ListeningStatsView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("53.760")).toBeTruthy());
    expect(screen.getByText("3.319")).toBeTruthy();
    expect(screen.getByText("812")).toBeTruthy();
  });

  it("states the unmatched share above the charts rather than hiding it", async () => {
    render(ListeningStatsView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText(/62%/)).toBeTruthy());
    expect(screen.getByText(/33\.461/)).toBeTruthy();
  });

  it("says how little of the listening time was actually measured", async () => {
    render(ListeningStatsView, { onnavigate: vi.fn() });

    // 876 of 53.760 listens reported a duration, so the estimate is mostly assumed.
    await waitFor(() => expect(screen.getByText(/Maar 2% \(876\)/)).toBeTruthy());
  });

  it("ranks the tracks, artists and labels it could link", async () => {
    render(ListeningStatsView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    expect(screen.getByText("Nosferatu")).toBeTruthy();
    expect(screen.getByText("Peacock Records")).toBeTruthy();
    expect(screen.getByText("listenbrainz_import")).toBeTruthy();
  });

  it("names an unknown artist rather than leaving the line blank", async () => {
    render(ListeningStatsView, { onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText(/onbekende artiest/i)).toBeTruthy());
  });

  it("navigates to an artist from the ranking", async () => {
    const onnavigate = vi.fn();
    render(ListeningStatsView, { onnavigate });

    await waitFor(() => expect(screen.getByText("Nosferatu")).toBeTruthy());
    await fireEvent.click(screen.getByText("Nosferatu"));
    expect(onnavigate).toHaveBeenCalledWith("artist:7");
  });

  it("reloads with a different bucket when the period changes", async () => {
    render(ListeningStatsView, { onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("53.760")).toBeTruthy());

    await fireEvent.click(screen.getByText("30 dagen"));

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => String(url).includes("bucket=day"))).toBe(
        true,
      ),
    );
  });

  it("asks the server for the browser's timezone, not for UTC", async () => {
    render(ListeningStatsView, { onnavigate: vi.fn() });
    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(String(globalThis.fetch.mock.calls[0][0])).toContain("tz=");
  });

  it("says so when the history is empty instead of drawing empty charts", async () => {
    globalThis.fetch = listeningApi({ summary: { ...SUMMARY, listens: 0 } });
    render(ListeningStatsView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText(/niets geluisterd/i)).toBeTruthy());
  });

  it("says so when the endpoint is unavailable", async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, json: async () => ({}) }));
    render(ListeningStatsView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText(/niet beschikbaar/i)).toBeTruthy());
  });

  it("shows the genre breakdown and says the bars overlap", async () => {
    render(ListeningStatsView, { onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByTestId("genre-panel")).toBeTruthy());
    const panel = screen.getByTestId("genre-panel");
    expect(panel.textContent).toContain("Uptempo Hardcore");
    expect(panel.textContent).toMatch(/overlappen/);
    expect(panel.textContent).toContain("7.000");
  });

  it("toggles a genre filter from its bar, reloads every panel and writes the URL", async () => {
    render(ListeningStatsView, { onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByTestId("genre-panel")).toBeTruthy());

    const bar = screen.getByRole("button", { name: /^Hardcore/ });
    await fireEvent.click(bar);

    await waitFor(() =>
      expect(callsTo("top-artists").some((url) => url.includes("genre=Hardcore"))).toBe(true),
    );
    for (const path of [
      "summary",
      "timeline",
      "clock",
      "sources",
      "top-tracks",
      "top-labels",
      "years",
    ]) {
      expect(
        callsTo(path).some((url) => url.includes("genre=Hardcore")),
        path,
      ).toBe(true);
    }
    expect(window.location.search).toBe("?genre=Hardcore");
    await waitFor(() => expect(bar.getAttribute("aria-pressed")).toBe("true"));
  });

  it("toggles a release year from its bar", async () => {
    render(ListeningStatsView, { onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByTestId("year-panel")).toBeTruthy());

    await fireEvent.click(screen.getByRole("button", { name: /^2019: / }));
    await waitFor(() => expect(window.location.search).toBe("?year=2019"));
    expect(screen.getByTestId("active-filters").textContent).toContain("2019");
  });

  it("selects a decade as a range in the decade view", async () => {
    render(ListeningStatsView, { onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByTestId("year-panel")).toBeTruthy());

    await fireEvent.click(screen.getByRole("button", { name: "Decennium" }));
    await fireEvent.click(screen.getByRole("button", { name: /^Jaren 2010/ }));
    await waitFor(() => expect(window.location.search).toBe("?year_from=2010&year_to=2019"));
  });

  it("opens a shared link with its filter applied", async () => {
    window.history.replaceState(null, "", "/listening?period=all&genre=Hardstyle&year=unknown");
    render(ListeningStatsView, { onnavigate: vi.fn() });

    await waitFor(() => expect(callsTo("summary").length).toBeGreaterThan(0));
    const [url] = callsTo("summary");
    expect(url).toContain("genre=Hardstyle");
    expect(url).toContain("year=unknown");
    expect(url).not.toContain("from=");
  });

  it("names the unmatched listens a filter excludes, next to the filter", async () => {
    window.history.replaceState(null, "", "/listening?genre=Hardstyle");
    globalThis.fetch = listeningApi({
      summary: {
        ...SUMMARY,
        listens: 9000,
        matched: 9000,
        unmatched: 0,
        filtered: true,
        excluded_unmatched: 33461,
      },
    });
    render(ListeningStatsView, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByTestId("excluded-unmatched")).toBeTruthy());
    expect(screen.getByTestId("excluded-unmatched").textContent).toMatch(
      /33\.461 luisterbeurten zonder gekoppelde track/,
    );
    // The unfiltered caveat would read "0%" here, which is true and misleading.
    expect(screen.queryByText(/nooit aan een track in de bibliotheek gekoppeld/)).toBeNull();
  });

  it("clears every filter at once", async () => {
    window.history.replaceState(null, "", "/listening?genre=Hardstyle&year=2019");
    render(ListeningStatsView, { onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Filters wissen")).toBeTruthy());

    await fireEvent.click(screen.getByText("Filters wissen"));
    await waitFor(() => expect(window.location.search).toBe(""));
    expect(screen.queryByTestId("active-filters")).toBeNull();
  });

  it("says a filtered view is empty in the filter's own words", async () => {
    window.history.replaceState(null, "", "/listening?genre=Polka");
    globalThis.fetch = listeningApi({
      summary: { ...SUMMARY, listens: 0, filtered: true, excluded_unmatched: 5 },
    });
    render(ListeningStatsView, { onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText(/dat aan dit filter voldoet/)).toBeTruthy());
  });
});
