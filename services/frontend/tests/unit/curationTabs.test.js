import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/svelte";
import { get } from "svelte/store";
import FestivalsTab from "../../src/lib/management/tabs/FestivalsTab.svelte";
import LineupsTab from "../../src/lib/management/tabs/LineupsTab.svelte";
import LabelsTab from "../../src/lib/management/tabs/LabelsTab.svelte";
import { activeView, activeManagementTab } from "../../src/lib/store.js";

function props(overrides = {}) {
  return {
    API_BASE: "http://muma",
    getHeaders: (extra = {}) => ({ "x-api-key": "key", ...extra }),
    onMessage: vi.fn(),
    onError: vi.fn(),
    ...overrides,
  };
}

const writes = () =>
  globalThis.fetch.mock.calls
    .filter(([, o]) => o?.method && o.method !== "GET")
    .map(([url, o]) => ({ url, method: o.method, body: o.body ? JSON.parse(o.body) : null }));

afterEach(() => vi.restoreAllMocks());

describe("FestivalsTab", () => {
  const FESTIVALS = [
    {
      id: 1,
      name: "Defqon.1",
      active: true,
      aliases: ["Defqon 1"],
      editions: [{ year: 2025, date: "2025-06-27" }],
    },
    { id: 4, name: "Sunrise", active: false, aliases: [], editions: [] },
  ];

  beforeEach(() => {
    globalThis.fetch = vi.fn(async (url, options = {}) => {
      if (url.endsWith("/probe"))
        return {
          ok: true,
          json: async () => ({
            matches: [{ festival: "Defqon.1", year: 2025, date: "2025-06-27" }],
          }),
        };
      if (options.method) return { ok: true, json: async () => ({ status: "ok", id: 9 }) };
      return { ok: true, json: async () => FESTIVALS };
    });
  });

  it("lists festivals with their spellings, editions and state", async () => {
    render(FestivalsTab, props());
    await waitFor(() => expect(screen.getByText("Defqon.1")).toBeTruthy());
    expect(screen.getByText("Defqon 1")).toBeTruthy();
    expect(screen.getByText("2025 · 2025-06-27")).toBeTruthy();
    expect(screen.getByText("Inactief")).toBeTruthy();
  });

  it("creates a festival from the form", async () => {
    const onMessage = vi.fn();
    render(FestivalsTab, props({ onMessage }));
    await waitFor(() => expect(screen.getByText("Defqon.1")).toBeTruthy());

    await fireEvent.click(screen.getByRole("button", { name: /Nieuw festival/ }));
    const form = screen.getByTestId("festival-form");
    await fireEvent.input(within(form).getByLabelText("Naam"), { target: { value: "Dominator" } });
    await fireEvent.click(within(form).getByRole("button", { name: "Opslaan" }));

    await waitFor(() => expect(writes().length).toBe(1));
    expect(writes()[0]).toEqual({
      url: "http://muma/api/rules/festivals",
      method: "POST",
      body: { name: "Dominator", active: true, aliases: [], editions: [] },
    });
    expect(onMessage).toHaveBeenCalledWith("Dominator opgeslagen.");
  });

  it("edits an existing festival through PUT", async () => {
    render(FestivalsTab, props());
    await waitFor(() => expect(screen.getByText("Defqon.1")).toBeTruthy());

    await fireEvent.click(screen.getByLabelText("Defqon.1 bewerken"));
    const form = screen.getByTestId("festival-form");
    await fireEvent.click(within(form).getByRole("button", { name: "Opslaan" }));

    await waitFor(() => expect(writes().length).toBe(1));
    expect(writes()[0].url).toBe("http://muma/api/rules/festivals/1");
    expect(writes()[0].method).toBe("PUT");
    expect(writes()[0].body.aliases).toEqual(["Defqon 1"]);
  });

  it("probes a text against the saved rules", async () => {
    render(FestivalsTab, props());
    await waitFor(() => expect(screen.getByText("Defqon.1")).toBeTruthy());

    await fireEvent.input(screen.getByLabelText("Test een tekst"), {
      target: { value: "Defqon 1 2025 RED" },
    });
    await fireEvent.click(screen.getByRole("button", { name: "Herkennen" }));

    await waitFor(() =>
      expect(screen.getByTestId("probe-result").textContent).toMatch(
        /Defqon\.1\s*·\s*2025\s*·\s*2025-06-27/,
      ),
    );
  });
});

describe("LineupsTab", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(async (url, options = {}) => {
      if (url.endsWith("/api/rules/lineups/match")) {
        return {
          ok: true,
          json: async () => ({
            names: ["Angerfist", "Outsiders"],
            match: {
              matched: ["Angerfist"],
              unmatched: ["Outsiders"],
              suggestions: { Outsiders: ["The Outside Agency"] },
            },
          }),
        };
      }
      if (options.method === "PUT") {
        return {
          ok: true,
          json: async () => ({
            status: "ok",
            id: "Defqon.1/2025",
            names: ["Angerfist", "The Outside Agency"],
            match: { matched: ["Angerfist", "The Outside Agency"], unmatched: [], suggestions: {} },
          }),
        };
      }
      if (url.includes("/api/rules/lineups/Defqon.1")) {
        return {
          ok: true,
          json: async () => ({
            id: "Defqon.1/2014/RED",
            names: ["Angerfist", "Miss K8"],
            match: { matched: ["Angerfist", "Miss K8"], unmatched: [], suggestions: {} },
          }),
        };
      }
      return {
        ok: true,
        json: async () => ({
          root: "/mnt/music/metadata/festival-lineups",
          lineups: [
            {
              id: "Defqon.1/2014/RED",
              festival: "Defqon.1",
              year: "2014",
              stage: "RED",
              artists: 2,
            },
          ],
        }),
      };
    });
  });

  it("lists files by festival and opens one into the editor", async () => {
    render(LineupsTab, props());
    await waitFor(() => expect(screen.getByText("2014 · RED")).toBeTruthy());

    await fireEvent.click(screen.getByText("2014 · RED"));

    await waitFor(() => expect(screen.getByLabelText("Line-up").value).toBe("Angerfist\nMiss K8"));
    expect(screen.getByText("Alles matcht.")).toBeTruthy();
  });

  it("checks a pasted bill and takes a suggestion with one click", async () => {
    render(LineupsTab, props());
    await waitFor(() => expect(screen.getByText("2014 · RED")).toBeTruthy());

    await fireEvent.input(screen.getByLabelText("Line-up"), {
      target: { value: "Angerfist\nOutsiders" },
    });
    await fireEvent.click(screen.getByRole("button", { name: "Controleren" }));

    await waitFor(() =>
      expect(screen.getByText("1 van 2 namen matcht de bibliotheek")).toBeTruthy(),
    );
    await fireEvent.click(screen.getByRole("button", { name: "The Outside Agency" }));
    expect(screen.getByLabelText("Line-up").value).toBe("Angerfist\nThe Outside Agency");
  });

  it("writes the lineup and says what matched", async () => {
    const onMessage = vi.fn();
    render(LineupsTab, props({ onMessage }));
    await waitFor(() => expect(screen.getByText("2014 · RED")).toBeTruthy());

    const editor = screen.getByTestId("lineup-editor");
    const [festival, year] = within(editor).getAllByRole("textbox");
    await fireEvent.input(festival, { target: { value: "Defqon.1" } });
    await fireEvent.input(year, { target: { value: "2025" } });
    await fireEvent.input(screen.getByLabelText("Line-up"), {
      target: { value: "Angerfist\nThe Outside Agency" },
    });
    await fireEvent.click(within(editor).getByRole("button", { name: "Opslaan" }));

    await waitFor(() => expect(writes().length).toBe(1));
    expect(writes()[0].body).toEqual({
      festival: "Defqon.1",
      year: 2025,
      stage: null,
      text: "Angerfist\nThe Outside Agency",
    });
    expect(onMessage).toHaveBeenCalledWith("Defqon.1/2025 opgeslagen: 2 van 2 namen matchen.");
  });
});

describe("LabelsTab", () => {
  beforeEach(() => {
    activeView.set("management");
    activeManagementTab.set("labels");
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        total: 1,
        rows: [
          {
            id: 3,
            name: "Masters of Hardcore",
            mbid: null,
            parent_name: null,
            track_count: 812,
            catid_count: 2,
            genre_count: 0,
          },
        ],
        limit: 100,
        offset: 0,
      }),
    }));
  });

  it("lists labels and flags the ones without a genre rule", async () => {
    render(LabelsTab, props());
    await waitFor(() => expect(screen.getByText("Masters of Hardcore")).toBeTruthy());
    expect(screen.getByText("812")).toBeTruthy();
    expect(screen.getByText("geen")).toBeTruthy();
  });

  it("opens the edit page for a label", async () => {
    render(LabelsTab, props());
    await waitFor(() => expect(screen.getByText("Masters of Hardcore")).toBeTruthy());

    await fireEvent.click(screen.getByLabelText("Masters of Hardcore bewerken"));

    expect(get(activeView)).toBe("label-edit:Masters of Hardcore");
  });

  it("links to the proposals queue", async () => {
    render(LabelsTab, props());
    await waitFor(() => expect(screen.getByText("Masters of Hardcore")).toBeTruthy());

    await fireEvent.click(screen.getByRole("button", { name: /Labelvoorstellen/ }));

    expect(get(activeManagementTab)).toBe("label-proposals");
  });
});
