import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/svelte";
import ArtistCurationTab from "../../src/lib/management/tabs/ArtistCurationTab.svelte";

const PREMIERE = {
  id: 1,
  name: "Premiere",
  track_count: 9180,
  state: "unknown",
  canonical_name: null,
  decided_at: null,
  decided_by: null,
  proposal_kind: "reject",
  proposal_target: null,
  proposal_evidence: ["nothing left after removing noise"],
  proposal_confidence: 95,
};
const DJ_ANGERFIST = {
  id: 2,
  name: "DJ Angerfist",
  track_count: 5,
  state: "unknown",
  canonical_name: null,
  decided_at: null,
  decided_by: null,
  proposal_kind: "rewrite",
  proposal_target: "Angerfist",
  proposal_evidence: ["same name as 'Angerfist' without the DJ/MC prefix (300 tracks against 5)"],
  proposal_confidence: 80,
};
const BOAZ = {
  id: 3,
  name: "Boaz Van De Beatz",
  track_count: 40,
  state: "unknown",
  canonical_name: null,
  decided_at: null,
  decided_by: null,
  proposal_kind: "unknown",
  proposal_target: null,
  proposal_evidence: ["no mechanical match"],
  proposal_confidence: 0,
};
const SUMMARY = {
  in_library: 46885,
  unknown: 44227,
  white: 12,
  black: 2658,
  proposals: { reject: 267, rewrite: 1597 },
  analyzed_at: "2026-09-16 04:00:00",
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

function mockApi({
  rows = [PREMIERE, DJ_ANGERFIST, BOAZ],
  summary = SUMMARY,
  decisionOk = true,
} = {}) {
  return vi.fn(async (url, options = {}) => {
    if (url.includes("/api/rules/artists/summary")) return { ok: true, json: async () => summary };
    if (url.includes("/api/rules/artists/analyze/")) {
      return { ok: true, json: async () => ({ status: "finished", total: 3 }) };
    }
    if (url.includes("/api/rules/artists/analyze")) {
      return { ok: true, json: async () => ({ status: "queued", job_id: "artist-analysis-1" }) };
    }
    if (options.method === "POST" || options.method === "DELETE") {
      return { ok: decisionOk, json: async () => ({ detail: "Afgewezen" }) };
    }
    return { ok: true, json: async () => ({ total: rows.length, rows, limit: 100, offset: 0 }) };
  });
}

const posts = () =>
  globalThis.fetch.mock.calls
    .filter(([, options]) => options?.method === "POST")
    .map(([url, options]) => ({ url, body: options.body ? JSON.parse(options.body) : null }));

describe("ArtistCurationTab", () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the queue with the advice per name", async () => {
    render(ArtistCurationTab, props());

    await waitFor(() => expect(screen.getByText("Premiere")).toBeTruthy());
    expect(screen.getAllByText("Advies: verwijderen").length).toBeGreaterThan(0);
    expect(screen.getByText("Advies: samenvoegen met Angerfist")).toBeTruthy();
    expect(screen.getByText("nothing left after removing noise")).toBeTruthy();
    expect(screen.getAllByText("Geen advies").length).toBeGreaterThan(0);
    // The summary tiles.
    expect(within(screen.getByTestId("artist-summary")).getByText("44.227")).toBeTruthy();
    expect(screen.getByText("Laatste analyse: 2026-09-16 04:00:00")).toBeTruthy();
  });

  it("marks a name the tagger does not trust yet as new", async () => {
    globalThis.fetch = mockApi({
      rows: [
        { ...BOAZ, pending: true },
        { ...PREMIERE, pending: false },
      ],
    });
    render(ArtistCurationTab, props());

    await waitFor(() => expect(screen.getByText("Premiere")).toBeTruthy());
    const pendingRow = screen.getByText("Boaz Van De Beatz").closest("tr");
    expect(within(pendingRow).getByText("Nieuw")).toBeTruthy();
    const trustedRow = screen.getByText("Premiere").closest("tr");
    expect(within(trustedRow).queryByText("Nieuw")).toBeNull();
  });

  it("asks for the undecided names first, most tracks first", async () => {
    render(ArtistCurationTab, props());

    await waitFor(() => expect(screen.getByText("Premiere")).toBeTruthy());
    const url = globalThis.fetch.mock.calls.find(([u]) => u.includes("/api/rules/artists?"))[0];
    expect(url).toContain("state=unknown");
    expect(url).toContain("limit=100");
  });

  it("rejects one name and says so", async () => {
    const onMessage = vi.fn();
    render(ArtistCurationTab, props({ onMessage }));
    await waitFor(() => expect(screen.getByText("Premiere")).toBeTruthy());

    const row = screen.getByText("Premiere").closest("tr");
    await fireEvent.click(within(row).getByRole("button", { name: /Afkeuren/ }));

    await waitFor(() => expect(posts().length).toBe(1));
    expect(posts()[0].body).toEqual({ names: ["Premiere"], state: "black", canonical_name: null });
    expect(onMessage).toHaveBeenCalledWith("Premiere afgekeurd.");
  });

  it("follows the advice of a selected page in as few calls as possible", async () => {
    render(ArtistCurationTab, props());
    await waitFor(() => expect(screen.getByText("Premiere")).toBeTruthy());

    await fireEvent.click(screen.getByLabelText("Alles op deze pagina selecteren"));
    expect(screen.getByTestId("bulk-bar")).toBeTruthy();
    expect(screen.getByText("3 geselecteerd")).toBeTruthy();

    await fireEvent.click(screen.getByRole("button", { name: /Advies opvolgen \(2\)/ }));

    await waitFor(() => expect(posts().length).toBe(2));
    expect(posts().map((p) => p.body)).toEqual([
      { names: ["Premiere"], state: "black", canonical_name: null },
      { names: ["DJ Angerfist"], state: "black", canonical_name: "Angerfist" },
    ]);
  });

  it("corrects a name through the dialog, prefilled with the advice", async () => {
    const onMessage = vi.fn();
    render(ArtistCurationTab, props({ onMessage }));
    await waitFor(() => expect(screen.getByText("DJ Angerfist")).toBeTruthy());

    const row = screen.getByText("DJ Angerfist").closest("tr");
    await fireEvent.click(within(row).getByRole("button", { name: /Corrigeren/ }));

    const input = screen.getByPlaceholderText("Juiste spelling…");
    expect(input.value).toBe("Angerfist");
    await fireEvent.click(screen.getByRole("button", { name: "Opslaan" }));

    await waitFor(() => expect(posts().length).toBe(1));
    expect(posts()[0].body).toEqual({
      names: ["DJ Angerfist"],
      state: "black",
      canonical_name: "Angerfist",
    });
    expect(onMessage).toHaveBeenCalledWith("DJ Angerfist wordt voortaan vervangen door Angerfist.");
  });

  it("surfaces the server's reason when a decision is refused", async () => {
    globalThis.fetch = mockApi({ decisionOk: false });
    const onError = vi.fn();
    render(ArtistCurationTab, props({ onError }));
    await waitFor(() => expect(screen.getByText("Premiere")).toBeTruthy());

    const row = screen.getByText("Premiere").closest("tr");
    await fireEvent.click(within(row).getByRole("button", { name: /Goedkeuren/ }));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Afgewezen"));
  });

  it("starts the analysis by itself when there has never been one", async () => {
    globalThis.fetch = mockApi({ summary: { ...SUMMARY, analyzed_at: null } });
    const onMessage = vi.fn();
    render(ArtistCurationTab, props({ onMessage }));

    await waitFor(() =>
      expect(
        globalThis.fetch.mock.calls.some(
          ([u, o]) => u.endsWith("/analyze") && o?.method === "POST",
        ),
      ).toBe(true),
    );
    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith("Analyse klaar: advies voor 3 namen."),
    );
  });

  it("does not start an analysis on its own once one has run", async () => {
    render(ArtistCurationTab, props());
    await waitFor(() => expect(screen.getByText("Premiere")).toBeTruthy());

    expect(
      globalThis.fetch.mock.calls.some(([u, o]) => u.endsWith("/analyze") && o?.method === "POST"),
    ).toBe(false);
  });

  // What the shared Management test mocks: every request answers with the same generic
  // body. The tab must not throw on that, or the whole management view test suite goes.
  it("survives a summary that is not a summary", async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => [] }));
    render(ArtistCurationTab, props());

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByTestId("artist-summary")).toBeNull());
  });

  it("lists what the evidence run approved, newest first, on the approved tab", async () => {
    render(ArtistCurationTab, props());
    await waitFor(() => expect(screen.getByText("Premiere")).toBeTruthy());
    expect(screen.queryByText("Automatisch (bewijsronde)")).toBeNull();

    await fireEvent.click(screen.getByRole("button", { name: "Goedgekeurd" }));
    await fireEvent.click(await screen.findByText("Automatisch (bewijsronde)"));

    await waitFor(() =>
      expect(
        globalThis.fetch.mock.calls.some(
          ([u]) =>
            u.includes("state=white") &&
            u.includes("decided_by=auto-external") &&
            u.includes("sort=decided"),
        ),
      ).toBe(true),
    );
  });

  it("undoes a decision on a decided row", async () => {
    globalThis.fetch = mockApi({
      rows: [
        { ...PREMIERE, state: "black", decided_at: "2026-09-16 04:00:00", decided_by: "user" },
      ],
    });
    render(ArtistCurationTab, props());
    await waitFor(() => expect(screen.getByText("Premiere")).toBeTruthy());
    expect(screen.getByText(/door user/)).toBeTruthy();

    await fireEvent.click(screen.getByLabelText("Beslissing over Premiere ongedaan maken"));

    await waitFor(() =>
      expect(
        globalThis.fetch.mock.calls.some(
          ([u, o]) => o?.method === "DELETE" && u.endsWith("/api/rules/artists/Premiere"),
        ),
      ).toBe(true),
    );
  });
});
