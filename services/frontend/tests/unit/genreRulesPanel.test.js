import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import GenreRulesPanel from "../../src/lib/management/GenreRulesPanel.svelte";
import GenreOverviewPanel from "../../src/lib/management/GenreOverviewPanel.svelte";
import { activeView } from "../../src/lib/store.js";

const WHITE = [
  { id: 72, name: "Hardcore" },
  { id: 57, name: "Frenchcore" },
];
const ARTIST_RULES = [
  {
    id: 1,
    artist_name: "Angerfist",
    genre_name: "Hardcore",
    genre_id: 72,
    artist_id: 9,
    track_count: 300,
    created_at: "2026-09-18 10:00:00",
    created_by: "demo-user",
  },
  {
    id: 2,
    artist_name: "Old Name",
    genre_name: "Frenchcore",
    genre_id: 57,
    artist_id: null,
    track_count: 0,
    created_at: null,
    created_by: null,
  },
];
const LABEL_RULES = [
  {
    id: 21,
    label_name: "Roughstate",
    genre_name: "Hardcore",
    genre_id: 72,
    label_id: 3,
    track_count: 40,
  },
];
const OVERVIEW = {
  total: 2,
  rows: [
    {
      id: 90,
      name: "Industrial Hardcore",
      hardness: 80,
      track_count: 1514,
      artist_rule_count: 3,
      label_rule_count: 1,
      parents: ["Hardcore"],
    },
    {
      id: 149,
      name: "Trance",
      hardness: null,
      track_count: 658,
      artist_rule_count: 0,
      label_rule_count: 0,
      parents: [],
    },
  ],
};

function props(overrides = {}) {
  return {
    API_BASE: "http://muma",
    getHeaders: (extra = {}) => ({ "x-api-key": "key", ...extra }),
    onMessage: vi.fn(),
    onError: vi.fn(),
    whiteGenres: WHITE,
    ...overrides,
  };
}

function mockApi({ ok = true } = {}) {
  return vi.fn(async (url, options = {}) => {
    if (options.method === "POST" || options.method === "DELETE") {
      return { ok, json: async () => ({ detail: "Geweigerd" }) };
    }
    if (url.includes("/api/rules/artist-genres"))
      return { ok: true, json: async () => ARTIST_RULES };
    if (url.includes("/api/rules/label-genres")) return { ok: true, json: async () => LABEL_RULES };
    if (url.includes("/api/artists?q="))
      return { ok: true, json: async () => [{ id: 9, name: "Angerfist" }] };
    if (url.includes("/api/curation/genres")) return { ok: true, json: async () => OVERVIEW };
    return { ok: true, json: async () => [] };
  });
}

const writes = () =>
  globalThis.fetch.mock.calls
    .filter(([, options]) => options?.method === "POST" || options?.method === "DELETE")
    .map(([url, options]) => ({
      url,
      method: options.method,
      body: options.body ? JSON.parse(options.body) : null,
    }));

describe("GenreRulesPanel", () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
    activeView.set("");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists the artist rules with their reach and provenance", async () => {
    render(GenreRulesPanel, props({ kind: "artist" }));

    await waitFor(() => expect(screen.getByText("Angerfist")).toBeTruthy());
    expect(screen.getByText("300")).toBeTruthy();
    expect(screen.getByText(/demo-user ·/)).toBeTruthy();
    // A rule whose artist left the library says so and cannot be opened.
    expect(screen.getByText("niet in bibliotheek")).toBeTruthy();
    expect(screen.getAllByText("Bewerken")).toHaveLength(1);
  });

  it("lists the label rules under the label kind", async () => {
    render(GenreRulesPanel, props({ kind: "label" }));

    await waitFor(() => expect(screen.getByText("Roughstate")).toBeTruthy());
    const urls = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.endsWith("/api/rules/label-genres"))).toBe(true);
  });

  it("filters on name or genre without another request", async () => {
    render(GenreRulesPanel, props({ kind: "artist" }));
    await waitFor(() => expect(screen.getByText("Angerfist")).toBeTruthy());
    globalThis.fetch.mockClear();

    await fireEvent.input(screen.getByPlaceholderText("Zoek op naam of genre..."), {
      target: { value: "french" },
    });

    expect(screen.queryByText("Angerfist")).toBeNull();
    expect(screen.getByText("Old Name")).toBeTruthy();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("cannot add a rule before both halves are filled, nor one that exists", async () => {
    render(GenreRulesPanel, props({ kind: "artist" }));
    await waitFor(() => expect(screen.getByText("Angerfist")).toBeTruthy());
    const button = screen.getByText("Regel toevoegen").closest("button");
    expect(button.disabled).toBe(true);

    await fireEvent.input(screen.getByLabelText("Artiest"), { target: { value: "Angerfist" } });
    await fireEvent.change(screen.getByLabelText("Kies Genre"), { target: { value: "72" } });

    expect(button.disabled).toBe(true);
    expect(screen.getByText("Die regel bestaat al.")).toBeTruthy();
  });

  it("adds a rule and reloads the list", async () => {
    const onMessage = vi.fn();
    render(GenreRulesPanel, props({ kind: "artist", onMessage }));
    await waitFor(() => expect(screen.getByText("Angerfist")).toBeTruthy());

    await fireEvent.input(screen.getByLabelText("Artiest"), { target: { value: "Outsiders" } });
    await fireEvent.change(screen.getByLabelText("Kies Genre"), { target: { value: "72" } });
    await fireEvent.click(screen.getByText("Regel toevoegen"));

    await waitFor(() => expect(writes()).toHaveLength(1));
    expect(writes()[0]).toEqual({
      url: "http://muma/api/rules/artist-genres",
      method: "POST",
      body: { artist_name: "Outsiders", genre_id: 72 },
    });
    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith("Outsiders krijgt voortaan Hardcore."),
    );
    const reloads = globalThis.fetch.mock.calls.filter(
      ([url, o]) => !o?.method && url.endsWith("/api/rules/artist-genres"),
    );
    expect(reloads.length).toBeGreaterThanOrEqual(2);
  });

  it("surfaces the server's reason when a rule is refused", async () => {
    globalThis.fetch = mockApi({ ok: false });
    const onError = vi.fn();
    render(GenreRulesPanel, props({ kind: "artist", onError }));
    await waitFor(() => expect(screen.getByText("Angerfist")).toBeTruthy());

    await fireEvent.input(screen.getByLabelText("Artiest"), { target: { value: "Outsiders" } });
    await fireEvent.change(screen.getByLabelText("Kies Genre"), { target: { value: "72" } });
    await fireEvent.click(screen.getByText("Regel toevoegen"));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Geweigerd"));
  });

  it("removes a rule and tells the parent something changed", async () => {
    const onchange = vi.fn();
    render(GenreRulesPanel, props({ kind: "artist", onchange }));
    await waitFor(() => expect(screen.getByText("Angerfist")).toBeTruthy());

    await fireEvent.click(screen.getByLabelText("Regel voor Angerfist verwijderen"));

    await waitFor(() =>
      expect(writes()).toEqual([
        { url: "http://muma/api/rules/artist-genres/1", method: "DELETE", body: null },
      ]),
    );
    await waitFor(() => expect(onchange).toHaveBeenCalled());
  });

  it("opens the artist's edit page from the row", async () => {
    render(GenreRulesPanel, props({ kind: "artist" }));
    await waitFor(() => expect(screen.getByText("Angerfist")).toBeTruthy());

    await fireEvent.click(screen.getByText("Bewerken"));

    expect(get(activeView)).toBe("artist-edit:9");
  });

  it("reports a list that could not be loaded", async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, json: async () => ({}) }));
    const onError = vi.fn();
    render(GenreRulesPanel, props({ kind: "artist", onError }));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Kon regels niet ophalen."));
  });
});

describe("GenreOverviewPanel", () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
    activeView.set("");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists the approved genres with hardness, parents and rule counts", async () => {
    render(GenreOverviewPanel, props());

    await waitFor(() => expect(screen.getByText("Industrial Hardcore")).toBeTruthy());
    expect(screen.getByText("1.514")).toBeTruthy();
    expect(screen.getByText("80")).toBeTruthy();
    expect(screen.getByText("Hardcore")).toBeTruthy();
    const urls = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.includes("/api/curation/genres?limit=1000"))).toBe(true);
  });

  it("filters by name or parent without another request", async () => {
    render(GenreOverviewPanel, props());
    await waitFor(() => expect(screen.getByText("Trance")).toBeTruthy());
    globalThis.fetch.mockClear();

    await fireEvent.input(screen.getByLabelText("Zoek genre of bovenliggend genre"), {
      target: { value: "hardcore" },
    });

    expect(screen.queryByText("Trance")).toBeNull();
    expect(screen.getByText("Industrial Hardcore")).toBeTruthy();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("opens the genre's edit page from the row", async () => {
    render(GenreOverviewPanel, props());
    await waitFor(() => expect(screen.getByText("Trance")).toBeTruthy());

    await fireEvent.click(screen.getAllByText("Bewerken")[1]);

    expect(get(activeView)).toBe("genre-edit:Trance");
  });

  it("reloads when a sibling panel changed the rules", async () => {
    const { rerender } = render(GenreOverviewPanel, props({ refreshKey: 0 }));
    await waitFor(() => expect(screen.getByText("Trance")).toBeTruthy());
    const before = globalThis.fetch.mock.calls.length;

    await rerender(props({ refreshKey: 1 }));

    await waitFor(() => expect(globalThis.fetch.mock.calls.length).toBe(before + 1));
  });
});
