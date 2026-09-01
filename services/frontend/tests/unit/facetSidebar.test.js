import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import FacetSidebar from "../../src/lib/management/library/FacetSidebar.svelte";

const GENRES = [
  { genre: "Hardcore", state: "white", count: 1200 },
  { genre: "Uptempo", state: "white", count: 400 },
  { genre: "Tribecore", state: "unknown", count: 12 },
];

function filters(overrides = {}) {
  return {
    artist: [],
    genre: [],
    bpm_min: null,
    bpm_max: null,
    year_min: null,
    year_max: null,
    analyzed: null,
    ...overrides,
  };
}

function props(overrides = {}) {
  return {
    API_BASE: "http://muma",
    getHeaders: () => ({ "x-api-key": "key" }),
    filters: filters(),
    genres: GENRES,
    onChange: vi.fn(),
    ...overrides,
  };
}

function checkboxFor(name) {
  return screen
    .getByText(new RegExp(`^${name}`))
    .closest("label")
    .querySelector("input");
}

describe("FacetSidebar", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => [{ artist: "Angerfist" }, { artist: "Angernoizer" }],
    }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("separates approved genres from the ones still to be curated", () => {
    render(FacetSidebar, props());

    expect(screen.getByText(/^Hardcore/)).toBeTruthy();
    expect(screen.getByText(/^Tribecore/)).toBeTruthy();
  });

  it("says so when no genres are indexed", () => {
    render(FacetSidebar, props({ genres: [] }));

    expect(screen.getByText(/Nog geen genres geïndexeerd/)).toBeTruthy();
  });

  it("ticking a genre reports it as a filter", async () => {
    const onChange = vi.fn();
    render(FacetSidebar, props({ onChange }));

    await fireEvent.change(checkboxFor("Hardcore"));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ genre: ["Hardcore"] }));
  });

  it("unticking a genre removes it again", async () => {
    const onChange = vi.fn();
    render(FacetSidebar, props({ filters: filters({ genre: ["Hardcore"] }), onChange }));

    await fireEvent.change(checkboxFor("Hardcore"));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ genre: [] }));
  });

  it("shows the artists that are already filtered on", () => {
    render(FacetSidebar, props({ filters: filters({ artist: ["Angerfist"] }) }));

    expect(screen.getByText(/Angerfist/)).toBeTruthy();
  });

  it("removes an artist that is clicked away", async () => {
    const onChange = vi.fn();
    render(FacetSidebar, props({ filters: filters({ artist: ["Angerfist"] }), onChange }));

    await fireEvent.click(screen.getByText(/Angerfist/));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ artist: [] }));
  });

  it("waits for two characters before searching for an artist", async () => {
    vi.useFakeTimers();
    render(FacetSidebar, props());

    await fireEvent.input(screen.getByPlaceholderText("Zoek artiest..."), {
      target: { value: "a" },
    });
    await vi.advanceTimersByTimeAsync(250);

    expect(globalThis.fetch).not.toHaveBeenCalled();
    vi.useRealTimers();
  });

  it("suggests artists once enough has been typed", async () => {
    render(FacetSidebar, props());

    await fireEvent.input(screen.getByPlaceholderText("Zoek artiest..."), {
      target: { value: "anger" },
    });

    await waitFor(() => expect(screen.getByText("Angernoizer")).toBeTruthy());
  });

  it("picking a suggestion adds it as a filter", async () => {
    const onChange = vi.fn();
    render(FacetSidebar, props({ onChange }));
    await fireEvent.input(screen.getByPlaceholderText("Zoek artiest..."), {
      target: { value: "anger" },
    });
    await waitFor(() => expect(screen.getByText("Angernoizer")).toBeTruthy());

    await fireEvent.click(screen.getByText("Angernoizer"));

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ artist: ["Angernoizer"] }));
    // The suggestion list is cleared; what remains is the chip for the active filter.
    expect(screen.getAllByText(/Angernoizer/)).toHaveLength(1);
  });

  it("an artist that is already filtered on is not added twice", async () => {
    const onChange = vi.fn();
    render(FacetSidebar, props({ filters: filters({ artist: ["Angernoizer"] }), onChange }));
    await fireEvent.input(screen.getByPlaceholderText("Zoek artiest..."), {
      target: { value: "anger" },
    });
    await waitFor(() => expect(screen.getAllByText("Angernoizer").length).toBeGreaterThan(1));

    await fireEvent.click(screen.getAllByText("Angernoizer").at(-1));

    expect(onChange).not.toHaveBeenCalled();
  });

  it("a failing artist search suggests nothing rather than breaking", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });
    render(FacetSidebar, props());

    await fireEvent.input(screen.getByPlaceholderText("Zoek artiest..."), {
      target: { value: "anger" },
    });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(screen.queryByText("Angernoizer")).toBeNull();
  });

  it("reports a bpm range", async () => {
    const onChange = vi.fn();
    render(FacetSidebar, props({ onChange }));

    await fireEvent.change(screen.getByPlaceholderText("min"), { target: { value: "150" } });

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ bpm_min: 150 }));
  });

  it("clearing a bound drops it from the filter", async () => {
    const onChange = vi.fn();
    render(FacetSidebar, props({ filters: filters({ bpm_min: 150 }), onChange }));

    await fireEvent.change(screen.getByPlaceholderText("min"), { target: { value: "" } });

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ bpm_min: null }));
  });

  it("reports a year range", async () => {
    const onChange = vi.fn();
    render(FacetSidebar, props({ onChange }));

    await fireEvent.change(screen.getByPlaceholderText("van"), { target: { value: "2020" } });
    await fireEvent.change(screen.getByPlaceholderText("tot"), { target: { value: "2024" } });

    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({ year_min: 2020, year_max: 2024 }),
    );
  });

  it("can narrow the selection to analysed tracks only", async () => {
    const onChange = vi.fn();
    render(FacetSidebar, props({ onChange }));

    await fireEvent.change(checkboxFor("Alleen geanalyseerd"), { target: { checked: true } });

    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ analyzed: true }));
  });
});
