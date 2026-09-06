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

describe("ListeningStatsView", () => {
  beforeEach(() => {
    globalThis.fetch = listeningApi();
  });

  afterEach(() => {
    vi.restoreAllMocks();
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
});
