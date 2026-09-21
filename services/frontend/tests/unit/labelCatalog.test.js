import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import LabelCatalog from "../../src/lib/curation/LabelCatalog.svelte";
import LabelEdit from "../../src/lib/curation/LabelEdit.svelte";
import { RUNS_SHOWN } from "../../src/lib/curation/catalogRuns";

const DWX = {
  prefix: "DWX",
  separator: "",
  min: 0,
  max: 2212,
  width: 4,
  present: 1921,
  releases: 1925,
  absent_count: 292,
  absent: [177, 223, 287, 288, 289],
  absent_runs: [
    [177, 177],
    [223, 223],
    [287, 289],
  ],
  absent_truncated: false,
  coverage: 0.868,
  variants: [{ catid: "DWX1105D", release_folder: "DWX1105D Some Digital Edition" }],
};

const CATALOG = {
  name: "Dirty Workz",
  files_considered: 5531,
  files_outside_root: 0,
  series: [DWX],
  other: [{ catid: "DWXFREE", release_folder: "DWXFREE Free Download" }],
};

function fetchAnswering(catalogResponse, labelBody = null) {
  return vi.fn(async (url) => {
    if (url.includes("/catalog")) return catalogResponse();
    if (url.includes("/api/curation/labels/")) return { ok: true, json: async () => labelBody };
    if (url.includes("/api/rules/genres")) return { ok: true, json: async () => [] };
    return { ok: true, json: async () => ({}) };
  });
}

const ok = (body) => () => ({ ok: true, json: async () => body });

let writeText;

beforeEach(() => {
  writeText = vi.fn(async () => {});
  Object.defineProperty(globalThis.navigator, "clipboard", {
    value: { writeText },
    configurable: true,
  });
  globalThis.fetch = fetchAnswering(ok(CATALOG));
});

afterEach(() => {
  vi.restoreAllMocks();
  delete globalThis.navigator.clipboard;
});

describe("the Catalogus section", () => {
  it("asks for the label's catalogue and shows one block per series", async () => {
    render(LabelCatalog, { name: "Dirty Workz" });

    await waitFor(() =>
      expect(screen.getByText("DWX · 0000–2212 · 1921 van 2213 aanwezig (87%)")).toBeTruthy(),
    );
    const called = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(called.some((url) => url.endsWith("/api/curation/labels/Dirty%20Workz/catalog"))).toBe(
      true,
    );
  });

  it("lists the absent numbers as runs with the series' padding", async () => {
    render(LabelCatalog, { name: "Dirty Workz" });

    await waitFor(() => expect(screen.getByText("DWX0177, DWX0223, DWX0287–DWX0289")).toBeTruthy());
    expect(screen.getByText("Niet aanwezig (292):")).toBeTruthy();
  });

  it("never says a number is missing, only that it is not present", async () => {
    render(LabelCatalog, { name: "Dirty Workz" });
    await waitFor(() => expect(screen.getByText(/Niet aanwezig/)).toBeTruthy());

    expect(screen.queryByText(/ontbreekt/i)).toBeNull();
    expect(screen.queryByText(/missing/i)).toBeNull();
  });

  it("shows variants and unreadable numbers with their folder as tooltip", async () => {
    render(LabelCatalog, { name: "Dirty Workz" });

    await waitFor(() => expect(screen.getByText("DWX1105D")).toBeTruthy());
    expect(screen.getByText("DWX1105D").getAttribute("title")).toBe(
      "DWX1105D Some Digital Edition",
    );
    expect(screen.getByText("DWXFREE").getAttribute("title")).toBe("DWXFREE Free Download");
  });

  it("copies every absent number, one per line, fully written out", async () => {
    render(LabelCatalog, { name: "Dirty Workz" });
    await waitFor(() => expect(screen.getByText("Kopieer als zoektermen")).toBeTruthy());

    await fireEvent.click(screen.getByText("Kopieer als zoektermen"));

    await waitFor(() => expect(screen.getByText("Gekopieerd")).toBeTruthy());
    expect(writeText).toHaveBeenCalledWith("DWX0177\nDWX0223\nDWX0287\nDWX0288\nDWX0289");
  });

  it("folds a long list of runs behind 'toon alles'", async () => {
    const runs = Array.from({ length: RUNS_SHOWN + 5 }, (_, i) => [i * 2 + 1, i * 2 + 1]);
    const series = { ...DWX, absent_runs: runs, absent_count: runs.length };
    globalThis.fetch = fetchAnswering(ok({ ...CATALOG, series: [series] }));
    render(LabelCatalog, { name: "Dirty Workz" });

    const toggle = await screen.findByText(`toon alles (${runs.length} reeksen)`);
    const last = `DWX${String((RUNS_SHOWN + 4) * 2 + 1).padStart(4, "0")}`;
    expect(screen.queryByText(new RegExp(last))).toBeNull();

    await fireEvent.click(toggle);

    await waitFor(() => expect(screen.getByText(new RegExp(last))).toBeTruthy());
    expect(screen.queryByText(/toon alles/)).toBeNull();
  });

  it("reports a series too wide to enumerate by count only, without a copy button", async () => {
    const series = {
      ...DWX,
      max: 2000000,
      absent: [],
      absent_runs: [],
      absent_truncated: true,
      absent_count: 1998079,
      coverage: 0.001,
    };
    globalThis.fetch = fetchAnswering(ok({ ...CATALOG, series: [series] }));
    render(LabelCatalog, { name: "Dirty Workz" });

    await waitFor(() => expect(screen.getByText(/te veel om op te sommen/)).toBeTruthy());
    expect(screen.queryByText("Kopieer als zoektermen")).toBeNull();
  });

  it("says when everything in the observed range is present", async () => {
    const series = { ...DWX, absent: [], absent_runs: [], absent_count: 0, coverage: 1 };
    globalThis.fetch = fetchAnswering(ok({ ...CATALOG, series: [series], other: [] }));
    render(LabelCatalog, { name: "Dirty Workz" });

    await waitFor(() =>
      expect(screen.getByText("Alles binnen het waargenomen bereik is aanwezig.")).toBeTruthy(),
    );
    expect(screen.queryByText("Kopieer als zoektermen")).toBeNull();
  });

  it("says how many of the label's files sit outside the EPs folder and were not counted", async () => {
    globalThis.fetch = fetchAnswering(ok({ ...CATALOG, files_outside_root: 171 }));
    render(LabelCatalog, { name: "Dirty Workz" });

    await waitFor(() =>
      expect(
        screen.getByText(
          "171 bestanden van dit label staan buiten de EPs-map en zijn niet meegeteld.",
        ),
      ).toBeTruthy(),
    );
  });

  it("shows an empty state when no folder carries a readable number", async () => {
    globalThis.fetch = fetchAnswering(ok({ ...CATALOG, series: [], other: [] }));
    render(LabelCatalog, { name: "Dirty Workz" });

    await waitFor(() =>
      expect(
        screen.getByText("Geen leesbare catalogusnummers in de mappen van dit label."),
      ).toBeTruthy(),
    );
  });

  it("keeps its own error when the catalogue cannot be loaded", async () => {
    globalThis.fetch = fetchAnswering(() => ({
      ok: false,
      status: 500,
      json: async () => ({ detail: "No database connection" }),
    }));
    render(LabelCatalog, { name: "Dirty Workz" });

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("No database connection");
  });

  it("reports a clipboard that refuses, next to the series", async () => {
    writeText.mockRejectedValueOnce(new Error("denied"));
    render(LabelCatalog, { name: "Dirty Workz" });
    await waitFor(() => expect(screen.getByText("Kopieer als zoektermen")).toBeTruthy());

    await fireEvent.click(screen.getByText("Kopieer als zoektermen"));

    await waitFor(() => expect(screen.getByText("Kopiëren is niet gelukt.")).toBeTruthy());
  });
});

describe("the label edit page", () => {
  const label = (over = {}) => ({
    name: "Dirty Workz",
    label_id: 3,
    mbid: null,
    parent_label_id: null,
    parent_label_name: null,
    in_library: true,
    external_ids: [],
    catids: ["DWX"],
    genre_rules: [],
    track_count: 5531,
    ...over,
  });

  it("renders the rest of the page before the catalogue has arrived", async () => {
    let release;
    const pending = new Promise((resolve) => {
      release = resolve;
    });
    globalThis.fetch = fetchAnswering(
      () => pending.then(() => ({ ok: true, json: async () => CATALOG })),
      label(),
    );
    render(LabelEdit, { name: "Dirty Workz", onback: vi.fn() });

    await waitFor(() => expect(screen.getByText("5531 tracks in de bibliotheek")).toBeTruthy());
    expect(screen.getByText("Catalogus laden…")).toBeTruthy();

    release();
    await waitFor(() => expect(screen.getByText(/1921 van 2213 aanwezig/)).toBeTruthy());
  });

  it("offers no catalogue for a label that is not in the library", async () => {
    globalThis.fetch = fetchAnswering(ok(CATALOG), label({ in_library: false, track_count: 0 }));
    render(LabelEdit, { name: "Dirty Workz", onback: vi.fn() });

    await waitFor(() => expect(screen.getByText(/Nog niet in de bibliotheek/)).toBeTruthy());
    expect(screen.queryByText("Catalogus")).toBeNull();
    const called = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(called.some((url) => url.includes("/catalog"))).toBe(false);
  });
});
