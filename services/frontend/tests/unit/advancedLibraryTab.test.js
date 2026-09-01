import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import AdvancedLibraryTab from "../../src/lib/management/tabs/AdvancedLibraryTab.svelte";

const TRACK = {
  id: 1,
  title: "Raise Your Fist",
  artist: "Angerfist",
  label: "Roughstate",
  bpm: 174,
  release_year: 2024,
  duration_secs: 240,
  genres: ["Hardcore"],
  file_path: "/music/a.mp3",
};

function props(overrides = {}) {
  return {
    API_BASE: "http://muma",
    getHeaders: (extra = {}) => ({ "x-api-key": "key", ...extra }),
    onMessage: vi.fn(),
    onError: vi.fn(),
    ...overrides,
  };
}

const SUMMARY = {
  tracks: 12345,
  artists: 678,
  labels: 90,
  genres: 42,
  total_duration_secs: 3600,
  coverage: { bpm: 80, genre: 90, artist: 95, analyzed: 70 },
};

function mockApi({
  tracks = [TRACK],
  total = 1,
  listFails = false,
  actionOk = true,
  detail = "Mislukt",
} = {}) {
  return vi.fn(async (url, options = {}) => {
    if (options.method === "POST") {
      return {
        ok: actionOk,
        status: actionOk ? 200 : 500,
        json: async () => ({ detail, message: "Download gestart." }),
      };
    }
    if (url.includes("/api/library/advanced")) {
      if (listFails)
        return { ok: false, status: 500, json: async () => ({ detail: "Database weg" }) };
      return { ok: true, json: async () => ({ tracks, total }) };
    }
    if (url.includes("/api/library/genres")) {
      return { ok: true, json: async () => [{ genre: "Hardcore", state: "white", count: 1200 }] };
    }
    if (url.includes("/api/analytics/summary")) return { ok: true, json: async () => SUMMARY };
    if (url.includes("/api/analytics/genre-distribution")) {
      return { ok: true, json: async () => [{ genre: "Hardcore", state: "white", count: 1200 }] };
    }
    if (url.includes("/api/analytics/bpm-histogram")) {
      return { ok: true, json: async () => [{ bucket_start: 150, count: 40 }] };
    }
    if (url.includes("/api/analytics/year-histogram")) {
      return { ok: true, json: async () => [{ year: 2024, count: 80 }] };
    }
    if (url.includes("/api/analytics/top-artists")) {
      return { ok: true, json: async () => [{ artist: "Angerfist", count: 210 }] };
    }
    if (url.includes("/api/analytics/top-labels")) {
      return { ok: true, json: async () => [{ label: "Roughstate", count: 95 }] };
    }
    return { ok: true, json: async () => ({}) };
  });
}

/** The tab batches its requests behind a 200ms timer. */
async function settle() {
  await vi.advanceTimersByTimeAsync(250);
}

async function renderLoaded(overrides = {}) {
  const rendered = render(AdvancedLibraryTab, props(overrides));
  await settle();
  await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
  return rendered;
}

function urlsFor(fragment) {
  return globalThis.fetch.mock.calls.map(([url]) => url).filter((url) => url.includes(fragment));
}

describe("AdvancedLibraryTab", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    globalThis.fetch = mockApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("loads the tracks and the aggregations on arrival", async () => {
    await renderLoaded();

    expect(urlsFor("/api/library/advanced")).toHaveLength(1);
    expect(urlsFor("/api/analytics/summary")).toHaveLength(1);
    expect(urlsFor("/api/library/genres")).toHaveLength(1);
  });

  it("reports a track list that could not be loaded", async () => {
    globalThis.fetch = mockApi({ listFails: true });
    render(AdvancedLibraryTab, props());

    await settle();

    await waitFor(() => expect(screen.queryByText("Raise Your Fist")).toBeNull());
  });

  it("searching on enter filters the list", async () => {
    await renderLoaded();

    const box = screen.getByPlaceholderText(/Zoek titel, artiest/);
    await fireEvent.input(box, { target: { value: "angerfist" } });
    await fireEvent.keyDown(box, { key: "Enter" });
    await settle();

    await waitFor(() =>
      expect(urlsFor("/api/library/advanced").some((url) => url.includes("q=angerfist"))).toBe(
        true,
      ),
    );
  });

  it("typing without enter does not search yet", async () => {
    await renderLoaded();
    const before = urlsFor("/api/library/advanced").length;

    await fireEvent.input(screen.getByPlaceholderText(/Zoek titel, artiest/), {
      target: { value: "anger" },
    });
    await settle();

    expect(urlsFor("/api/library/advanced")).toHaveLength(before);
  });

  it("one filter change fires one batch of requests", async () => {
    await renderLoaded();
    const before = urlsFor("/api/library/advanced").length;

    await fireEvent.click(screen.getAllByRole("checkbox")[0]);
    await settle();

    expect(urlsFor("/api/library/advanced")).toHaveLength(before + 1);
  });

  it("a filter can be cleared again", async () => {
    await renderLoaded();
    await fireEvent.click(screen.getAllByRole("checkbox")[0]);
    await settle();
    await waitFor(() => expect(screen.getByText(/Wis \(/)).toBeTruthy());

    await fireEvent.click(screen.getByText(/Wis \(/));
    await settle();

    await waitFor(() => expect(screen.queryByText(/Wis \(/)).toBeNull());
  });

  it("switching to the analysis view shows the aggregations", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByTitle("Analyse"));

    await waitFor(() => expect(screen.getByText("Genre-verdeling")).toBeTruthy());
  });

  it("switching back shows the track list again", async () => {
    await renderLoaded();
    await fireEvent.click(screen.getByTitle("Analyse"));
    await waitFor(() => expect(screen.getByText("Genre-verdeling")).toBeTruthy());

    await fireEvent.click(screen.getByTitle("Tracklijst"));

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
  });

  it("a re-analysis asks for confirmation first", async () => {
    window.confirm.mockReturnValue(false);
    await renderLoaded();
    await fireEvent.click(screen.getByText("Raise Your Fist"));
    await waitFor(() => expect(screen.getByText("Opnieuw analyseren")).toBeTruthy());

    await fireEvent.click(screen.getByText("Opnieuw analyseren"));

    expect(globalThis.fetch.mock.calls.some(([, o]) => o?.method === "POST")).toBe(false);
  });

  it("a confirmed re-analysis is started", async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });
    await fireEvent.click(screen.getByText("Raise Your Fist"));
    await waitFor(() => expect(screen.getByText("Opnieuw analyseren")).toBeTruthy());

    await fireEvent.click(screen.getByText("Opnieuw analyseren"));

    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith("Scan voor 'Raise Your Fist' gestart."),
    );
    expect(urlsFor("/rerun-parse")).toHaveLength(1);
  });

  it("reports a re-analysis the server refused", async () => {
    globalThis.fetch = mockApi({ actionOk: false, detail: "Bestand weg" });
    const onError = vi.fn();
    await renderLoaded({ onError });
    await fireEvent.click(screen.getByText("Raise Your Fist"));
    await waitFor(() => expect(screen.getByText("Opnieuw analyseren")).toBeTruthy());

    await fireEvent.click(screen.getByText("Opnieuw analyseren"));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Bestand weg"));
  });

  it("a confirmed redownload is started", async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });
    await fireEvent.click(screen.getByText("Raise Your Fist"));
    await waitFor(() => expect(screen.getByText("Opnieuw downloaden")).toBeTruthy());

    await fireEvent.click(screen.getByText("Opnieuw downloaden"));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Download gestart."));
    expect(urlsFor("/redownload")).toHaveLength(1);
  });

  it("reports a redownload the server refused", async () => {
    globalThis.fetch = mockApi({ actionOk: false, detail: "Geen bron" });
    const onError = vi.fn();
    await renderLoaded({ onError });
    await fireEvent.click(screen.getByText("Raise Your Fist"));
    await waitFor(() => expect(screen.getByText("Opnieuw downloaden")).toBeTruthy());

    await fireEvent.click(screen.getByText("Opnieuw downloaden"));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Geen bron"));
  });
});
