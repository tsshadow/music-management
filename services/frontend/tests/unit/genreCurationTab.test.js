import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import GenreCurationTab from "../../src/lib/management/tabs/GenreCurationTab.svelte";

const UNKNOWN_ROW = {
  id: 1,
  name: "Tribecore",
  state: "unknown",
  occurrences: 12,
  canonical_targets: [],
};
const WHITE_ROWS = [
  { id: 10, name: "Hardcore", state: "white" },
  { id: 11, name: "Uptempo Hardcore", state: "white" },
];
const ADVISED_ROWS = [
  {
    id: 1,
    name: "Upterror",
    state: "unknown",
    occurrences: 12,
    canonical_targets: [],
    proposal: {
      kind: "split",
      targets: [
        { id: 11, name: "Uptempo Hardcore" },
        { id: 12, name: "Terror" },
      ],
      evidence: ["blend: 'up' begins Uptempo Hardcore, 'terror' ends Terror"],
      confidence: 65,
    },
  },
  {
    id: 2,
    name: "Tafelpoot",
    state: "unknown",
    occurrences: 3,
    canonical_targets: [],
    proposal: {
      kind: "reject",
      targets: [],
      evidence: ["resembles no known genre"],
      confidence: 50,
    },
  },
  {
    id: 3,
    name: "Energycore",
    state: "unknown",
    occurrences: 209,
    canonical_targets: [],
    proposal: { kind: "unknown", targets: [], evidence: ["reads as a genre"], confidence: 0 },
  },
];
const SUMMARY = {
  unknown: 821,
  white: 271,
  black: 675,
  proposals: { rewrite: 126, split: 172, reject: 372, unknown: 151 },
  analyzed_at: "2026-09-18 10:00:00",
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

/** Answers the table request, the approved-genre request, the summary, the analysis and any decision. */
function mockApi({
  rows = [UNKNOWN_ROW],
  white = WHITE_ROWS,
  summary = SUMMARY,
  decisionOk = true,
  detail = "Afgewezen",
} = {}) {
  return vi.fn(async (url, options = {}) => {
    if (url.includes("/api/rules/genres/summary")) return { ok: true, json: async () => summary };
    if (url.includes("/api/rules/genres/analyze/")) {
      return { ok: true, json: async () => ({ status: "finished", total: rows.length }) };
    }
    if (url.includes("/api/rules/genres/analyze")) {
      return { ok: true, json: async () => ({ status: "queued", job_id: "genre-analysis-1" }) };
    }
    if (options.method === "POST") return { ok: decisionOk, json: async () => ({ detail }) };
    if (url.includes("state=white&limit=1000")) return { ok: true, json: async () => white };
    return { ok: true, json: async () => rows };
  });
}

async function renderLoaded(overrides = {}) {
  const rendered = render(GenreCurationTab, props(overrides));
  await waitFor(() => expect(screen.getByText("Tribecore")).toBeTruthy());
  return rendered;
}

function decisions() {
  return globalThis.fetch.mock.calls.filter(
    ([url, options]) => options?.method === "POST" && url.includes("/decide"),
  );
}

function analysisStarts() {
  return globalThis.fetch.mock.calls.filter(
    ([url, options]) => options?.method === "POST" && url.endsWith("/api/rules/genres/analyze"),
  );
}

describe("GenreCurationTab", () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("opens on the genres still waiting for a decision", async () => {
    await renderLoaded();

    const urls = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.includes("state=unknown&limit=500"))).toBe(true);
    expect(screen.getByText("12")).toBeTruthy();
  });

  it("loads the approved genres separately as correction targets", async () => {
    await renderLoaded();

    const urls = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.includes("state=white&limit=1000"))).toBe(true);
  });

  it("switching the filter reloads the table for that state", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByRole("button", { name: "Afgekeurd" }));

    await waitFor(() => {
      const urls = globalThis.fetch.mock.calls.map(([url]) => url);
      expect(urls.some((url) => url.includes("state=black&limit=500"))).toBe(true);
    });
  });

  it("the all filter asks for every state at once", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText("Alles"));

    await waitFor(() => {
      const urls = globalThis.fetch.mock.calls.map(([url]) => url);
      expect(urls.some((url) => url.endsWith("/api/rules/genres?limit=500"))).toBe(true);
    });
  });

  it("the search box narrows the table without another request", async () => {
    globalThis.fetch = mockApi({
      rows: [UNKNOWN_ROW, { id: 2, name: "Speedcore", state: "unknown", occurrences: 3 }],
    });
    await renderLoaded();
    globalThis.fetch.mockClear();

    await fireEvent.input(screen.getByPlaceholderText("Zoek genre..."), {
      target: { value: "speed" },
    });

    expect(screen.queryByText("Tribecore")).toBeNull();
    expect(screen.getByText("Speedcore")).toBeTruthy();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("reports a table that could not be loaded", async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, json: async () => ({}) }));
    const onError = vi.fn();

    render(GenreCurationTab, props({ onError }));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Kon genres niet ophalen."));
  });

  it("reports a table request that never arrived", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });
    const onError = vi.fn();

    render(GenreCurationTab, props({ onError }));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Netwerkfout bij ophalen genres."));
  });

  it("approving a genre straight from the table sends the decision", async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });

    await fireEvent.click(screen.getByText("Goedkeuren"));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Tribecore goedgekeurd."));
    const [url, options] = decisions()[0];
    expect(url).toBe("http://muma/api/rules/genres/1/decide");
    expect(JSON.parse(options.body).state).toBe("white");
  });

  it("rejecting a genre straight from the table sends the decision", async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });

    await fireEvent.click(screen.getByText("Afkeuren"));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Tribecore afgekeurd."));
    expect(JSON.parse(decisions()[0][1].body).state).toBe("black");
  });

  it("reports the reason a decision was refused", async () => {
    globalThis.fetch = mockApi({ decisionOk: false, detail: "Genre is in gebruik" });
    const onError = vi.fn();
    await renderLoaded({ onError });

    await fireEvent.click(screen.getByText("Goedkeuren"));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Genre is in gebruik"));
  });

  it("correcting a genre offers the approved genres to map it onto", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText("Corrigeren"));

    expect(screen.getByText("Hardcore")).toBeTruthy();
    expect(screen.getByText("Uptempo Hardcore")).toBeTruthy();
  });

  it("a correction is saved with every target that was ticked", async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });
    await fireEvent.click(screen.getByText("Corrigeren"));

    await fireEvent.click(screen.getAllByRole("checkbox")[1]);
    await fireEvent.click(screen.getByText("Opslaan"));

    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith(
        "Tribecore wordt voortaan vervangen door Uptempo Hardcore.",
      ),
    );
    expect(JSON.parse(decisions()[0][1].body).canonical_ids).toEqual([11]);
  });

  it("a target can be unticked again", async () => {
    await renderLoaded();
    await fireEvent.click(screen.getByText("Corrigeren"));

    await fireEvent.click(screen.getAllByRole("checkbox")[0]);
    await fireEvent.click(screen.getAllByRole("checkbox")[0]);
    await fireEvent.click(screen.getByText("Opslaan"));

    await waitFor(() => expect(JSON.parse(decisions()[0][1].body).canonical_ids).toEqual([]));
  });

  it("a correction can map one genre onto several approved ones", async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });
    await fireEvent.click(screen.getByText("Corrigeren"));

    await fireEvent.click(screen.getAllByRole("checkbox")[0]);
    await fireEvent.click(screen.getAllByRole("checkbox")[1]);
    await fireEvent.click(screen.getByText("Opslaan"));

    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith(
        "Tribecore wordt voortaan vervangen door Hardcore + Uptempo Hardcore.",
      ),
    );
  });

  it("an unknown genre is proposed for rejection by default", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText("Corrigeren"));
    await fireEvent.click(screen.getByText("Opslaan"));

    await waitFor(() => expect(JSON.parse(decisions()[0][1].body).state).toBe("black"));
  });

  it("the proposed state can be switched to approved", async () => {
    await renderLoaded();
    await fireEvent.click(screen.getByText("Corrigeren"));

    await fireEvent.click(screen.getAllByText("Goedkeuren")[1]);
    await fireEvent.click(screen.getByText("Opslaan"));

    await waitFor(() => expect(JSON.parse(decisions()[0][1].body).state).toBe("white"));
  });

  it("says so when there is nothing to correct onto", async () => {
    globalThis.fetch = mockApi({ white: [] });
    await renderLoaded();

    await fireEvent.click(screen.getByText("Corrigeren"));

    expect(screen.getByText("Nog geen goedgekeurde genres om naar te corrigeren.")).toBeTruthy();
  });

  it("cancelling closes the dialog without deciding anything", async () => {
    await renderLoaded();
    await fireEvent.click(screen.getByText("Corrigeren"));

    await fireEvent.click(screen.getByText("Annuleren"));

    expect(screen.queryByText("Opslaan")).toBeNull();
    expect(decisions()).toHaveLength(0);
  });

  it("shows the advice, its reasoning and its confidence next to a queued genre", async () => {
    globalThis.fetch = mockApi({ rows: ADVISED_ROWS });
    render(GenreCurationTab, props());

    await waitFor(() => expect(screen.getByText("Upterror")).toBeTruthy());
    expect(screen.getByText("Advies: vervangen door Uptempo Hardcore + Terror")).toBeTruthy();
    expect(
      screen.getByText("blend: 'up' begins Uptempo Hardcore, 'terror' ends Terror"),
    ).toBeTruthy();
    expect(screen.getByText("65%")).toBeTruthy();
    expect(screen.getByText("Advies: verwijderen")).toBeTruthy();
    expect(screen.getAllByText("Geen advies").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("821")).toBeTruthy();
    expect(screen.getByText("Laatste analyse: 2026-09-18 10:00:00")).toBeTruthy();
  });

  it("applies one row's advice as the decision it amounts to", async () => {
    globalThis.fetch = mockApi({ rows: ADVISED_ROWS });
    const onMessage = vi.fn();
    render(GenreCurationTab, props({ onMessage }));
    await waitFor(() => expect(screen.getByText("Upterror")).toBeTruthy());

    const [applyUpterror] = screen.getAllByText("Overnemen");
    await fireEvent.click(applyUpterror);

    await waitFor(() => expect(decisions()).toHaveLength(1));
    const [url, options] = decisions()[0];
    expect(url).toBe("http://muma/api/rules/genres/1/decide");
    expect(JSON.parse(options.body)).toEqual({ state: "black", canonical_ids: [11, 12] });
    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith(
        "Upterror wordt voortaan vervangen door Uptempo Hardcore.",
      ),
    );
  });

  it("offers no apply button where there is nothing to apply", async () => {
    globalThis.fetch = mockApi({ rows: ADVISED_ROWS });
    render(GenreCurationTab, props());
    await waitFor(() => expect(screen.getByText("Energycore")).toBeTruthy());

    // Upterror and Tafelpoot have advice to apply; Energycore does not.
    expect(screen.getAllByText("Overnemen")).toHaveLength(2);
  });

  it("applies the confident advice on the page in one click and says what it left alone", async () => {
    globalThis.fetch = mockApi({ rows: ADVISED_ROWS });
    const onMessage = vi.fn();
    render(GenreCurationTab, props({ onMessage }));
    await waitFor(() => expect(screen.getByText("Upterror")).toBeTruthy());

    // Tafelpoot's 50 sits under the floor, Energycore has nothing: one of three applies.
    await fireEvent.click(screen.getByText("Advies opvolgen (1)"));

    await waitFor(() => expect(decisions()).toHaveLength(1));
    expect(decisions()[0][0]).toBe("http://muma/api/rules/genres/1/decide");
    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith("1 adviezen opgevolgd, 2 laten staan."),
    );
  });

  it("narrows the queue to one kind of advice through the API", async () => {
    globalThis.fetch = mockApi({ rows: ADVISED_ROWS });
    render(GenreCurationTab, props());
    await waitFor(() => expect(screen.getByText("Upterror")).toBeTruthy());

    await fireEvent.click(screen.getByText("Verwijderen"));

    await waitFor(() => {
      const urls = globalThis.fetch.mock.calls.map(([url]) => url);
      expect(urls.some((url) => url.includes("state=unknown&proposal=reject&limit=500"))).toBe(
        true,
      );
    });
  });

  it("starts the analysis by itself when there has never been one", async () => {
    globalThis.fetch = mockApi({ summary: { ...SUMMARY, analyzed_at: null } });
    render(GenreCurationTab, props());

    await waitFor(() => expect(analysisStarts()).toHaveLength(1));
  });

  it("does not start an analysis on its own once one has run", async () => {
    await renderLoaded();

    expect(analysisStarts()).toHaveLength(0);
    expect(screen.getByText("Analyseren")).toBeTruthy();
  });

  it("runs the analysis on request and reloads afterwards", async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });

    await fireEvent.click(screen.getByText("Analyseren"));

    await waitFor(() => expect(analysisStarts()).toHaveLength(1));
    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith("Analyse klaar: advies voor 1 genres."),
    );
  });
});
