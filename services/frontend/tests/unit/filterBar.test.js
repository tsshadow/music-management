import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/svelte";
import FilterBar from "../../src/lib/FilterBar.svelte";
import { credentials, visibleSortOptions, isMobile } from "../../src/lib/store.js";

const GENRES = [
  { value: "Uptempo", songCount: 40 },
  { value: "Hardcore", songCount: 1200 },
  { value: "Obscure", songCount: 3 },
];

const YEARS = [{ value: "2023" }, { value: "2024" }];

function subsonic({ genres = GENRES, years = YEARS } = {}) {
  return vi.fn(async (url) => {
    if (url.includes("/rest/getGenres")) {
      return {
        ok: true,
        json: async () => ({ "subsonic-response": { genres: { genre: genres } } }),
      };
    }
    if (url.includes("/rest/getYears")) {
      return { ok: true, json: async () => ({ "subsonic-response": { years: { year: years } } }) };
    }
    return { ok: true, json: async () => ({ "subsonic-response": {} }) };
  });
}

async function renderLoaded(props = {}) {
  const rendered = render(FilterBar, { onchange: vi.fn(), ...props });
  await waitFor(() => expect(screen.getByText("Hardcore (1200)")).toBeTruthy());
  return rendered;
}

describe("FilterBar", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    visibleSortOptions.set({
      songs: ["recent", "alpha"],
      albums: ["newest"],
      artists: ["alphabetical"],
    });
    globalThis.fetch = subsonic();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("offers the genres the library actually has", async () => {
    await renderLoaded();

    expect(screen.getByText("Alle Genres")).toBeTruthy();
    expect(screen.getByText("Uptempo (40)")).toBeTruthy();
  });

  it("leaves out genres with almost nothing in them", async () => {
    await renderLoaded();

    expect(screen.queryByText("Obscure (3)")).toBeNull();
  });

  it("sorts the genres alphabetically", async () => {
    await renderLoaded();

    const options = [...screen.getByLabelText("Genres").options].map((option) =>
      option.textContent.trim(),
    );
    expect(options).toEqual(["Alle Genres", "Hardcore (1200)", "Uptempo (40)"]);
  });

  it("offers the release years newest first", async () => {
    await renderLoaded();

    const options = [...screen.getByLabelText("Jaar").options].map((option) =>
      option.textContent.trim(),
    );
    expect(options).toEqual(["Alle Jaren", "2024", "2023"]);
  });

  it("copes with a server that returns a single genre rather than a list", async () => {
    globalThis.fetch = subsonic({
      genres: { value: "Hardcore", songCount: 1200 },
      years: { value: "2024" },
    });

    await renderLoaded();

    expect(screen.getByText("Hardcore (1200)")).toBeTruthy();
    expect(screen.getByText("2024")).toBeTruthy();
  });

  it("survives a genre list that fails to load", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });

    render(FilterBar, { onchange: vi.fn() });

    await waitFor(() => expect(screen.getByText("Alle Genres")).toBeTruthy());
  });

  it("reports a genre choice to the parent", async () => {
    const onchange = vi.fn();
    await renderLoaded({ onchange });

    await fireEvent.change(screen.getByLabelText("Genres"), { target: { value: "Hardcore" } });

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ genre: "Hardcore" }));
  });

  it("reports a year choice to the parent", async () => {
    const onchange = vi.fn();
    await renderLoaded({ onchange });

    await fireEvent.change(screen.getByLabelText("Jaar"), { target: { value: "2024" } });

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ year: "2024" }));
  });

  it("reports a role choice to the parent", async () => {
    // The role filter only exists on the artists view.
    const onchange = vi.fn();
    render(FilterBar, { onchange, view: "artists" });
    await waitFor(() => expect(screen.getByLabelText("Rol")).toBeTruthy());

    await fireEvent.change(screen.getByLabelText("Rol"), { target: { value: "remixer" } });

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ role: "remixer" }));
  });

  it("reports a minimum rating to the parent", async () => {
    const onchange = vi.fn();
    await renderLoaded({ onchange });

    await fireEvent.change(screen.getByLabelText("Rating"), { target: { value: "4" } });

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ minRating: "4" }));
  });

  it("reports a quality floor to the parent", async () => {
    const onchange = vi.fn();
    await renderLoaded({ onchange });

    await fireEvent.change(screen.getByLabelText("Kwaliteit"), { target: { value: "320" } });

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ minQuality: "320" }));
  });

  it("reports whether unrated tracks are included", async () => {
    const onchange = vi.fn();
    await renderLoaded({ onchange });

    await fireEvent.click(screen.getByLabelText("Zonder rating"));

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ includeUnrated: false }));
  });

  it("reports a sort choice to the parent", async () => {
    const onchange = vi.fn();
    await renderLoaded({ onchange });

    await fireEvent.change(screen.getByLabelText("Sorteer op"), { target: { value: "alpha" } });

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ sort: "alpha" }));
  });

  it("only offers the sort options that are switched on", async () => {
    await renderLoaded();

    const options = [...screen.getByLabelText("Sorteer op").options].map((option) => option.value);
    expect(options).toEqual(["recent", "alpha"]);
  });

  it("offers the sort options belonging to the current view", async () => {
    render(FilterBar, { onchange: vi.fn(), view: "artists" });
    await waitFor(() => expect(screen.getByLabelText("Sorteer op")).toBeTruthy());

    const options = [...screen.getByLabelText("Sorteer op").options].map((option) => option.value);
    expect(options).toEqual(["alphabetical"]);
  });

  it("the genre filter can be hidden altogether", async () => {
    render(FilterBar, { onchange: vi.fn(), showGenre: false });

    await waitFor(() => expect(screen.getByText("Alle Jaren")).toBeTruthy());
    expect(screen.queryByLabelText("Genres")).toBeNull();
  });

  it("waits for the typing to settle before reporting a search", async () => {
    vi.useFakeTimers();
    const onchange = vi.fn();
    render(FilterBar, { onchange });

    await fireEvent.input(screen.getByRole("textbox"), { target: { value: "anger" } });
    await vi.advanceTimersByTimeAsync(400);
    expect(onchange).not.toHaveBeenCalled();

    await vi.advanceTimersByTimeAsync(100);
    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ search: "anger" }));
    vi.useRealTimers();
  });
});

describe("FilterBar phone chips", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    visibleSortOptions.set({
      songs: ["recent", "alpha"],
      albums: ["newest"],
      artists: ["alphabetical"],
    });
    globalThis.fetch = subsonic();
    isMobile.set(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    isMobile.set(false);
  });

  async function renderMobile(props = {}) {
    const rendered = render(FilterBar, { onchange: vi.fn(), ...props });
    await waitFor(() => expect(screen.getByTestId("mobile-filter-chips")).toBeTruthy());
    return rendered;
  }

  it("shows the chip row instead of the desktop panel", async () => {
    await renderMobile();

    expect(screen.getByTestId("mobile-filter-bar")).toBeTruthy();
    expect(screen.queryByLabelText("Genres")).toBeNull();
  });

  it("opens the genre sheet, picks an option, and reports it", async () => {
    const onchange = vi.fn();
    await renderMobile({ onchange });

    await fireEvent.click(screen.getByTestId("chip-genre"));
    const sheet = await screen.findByTestId("bottom-sheet");
    await fireEvent.click(within(sheet).getByText("Hardcore (1200)"));

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ genre: "Hardcore" }));
    await waitFor(() => expect(screen.queryByTestId("bottom-sheet")).toBeNull());
  });

  it("shows the chosen genre on the chip, filled in", async () => {
    await renderMobile({ genre: "Hardcore" });

    const chip = screen.getByTestId("chip-genre");
    expect(within(chip).getByText("Hardcore")).toBeTruthy();
  });

  it("clears an active filter from its chip without opening the sheet", async () => {
    const onchange = vi.fn();
    await renderMobile({ genre: "Hardcore", onchange });

    await fireEvent.click(screen.getByLabelText("Hardcore wissen"));

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ genre: "" }));
    expect(screen.queryByTestId("bottom-sheet")).toBeNull();
  });

  it("picks a quality floor from its sheet and clears it from the chip", async () => {
    const onchange = vi.fn();
    await renderMobile({ onchange });

    await fireEvent.click(screen.getByTestId("chip-quality"));
    const sheet = await screen.findByTestId("bottom-sheet");
    await fireEvent.click(within(sheet).getByText("Lossless"));

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ minQuality: "lossless" }));
    expect(within(screen.getByTestId("chip-quality")).getByText("Lossless")).toBeTruthy();

    await fireEvent.click(screen.getByLabelText("Lossless wissen"));
    expect(onchange).toHaveBeenLastCalledWith(expect.objectContaining({ minQuality: "" }));
  });

  it("picks a year from its sheet", async () => {
    const onchange = vi.fn();
    await renderMobile({ onchange });

    await fireEvent.click(screen.getByTestId("chip-year"));
    const sheet = await screen.findByTestId("bottom-sheet");
    await fireEvent.click(within(sheet).getByText("2024"));

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ year: "2024" }));
  });

  it("picks a sort option; the sort chip always shows the current choice", async () => {
    const onchange = vi.fn();
    await renderMobile({ onchange });

    expect(within(screen.getByTestId("chip-sort")).getByText("Recent uitgebracht")).toBeTruthy();

    await fireEvent.click(screen.getByTestId("chip-sort"));
    const sheet = await screen.findByTestId("bottom-sheet");
    await fireEvent.click(within(sheet).getByText("Alfabetisch"));

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ sort: "alpha" }));
  });

  it("toggles the unrated chip", async () => {
    const onchange = vi.fn();
    await renderMobile({ onchange });

    const chip = screen.getByTestId("chip-unrated");
    expect(chip.getAttribute("aria-pressed")).toBe("false");

    await fireEvent.click(chip);

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ includeUnrated: false }));
    expect(chip.getAttribute("aria-pressed")).toBe("true");
  });

  it("expands a compact search chip into an input", async () => {
    const onchange = vi.fn();
    vi.useFakeTimers();
    await renderMobile({ onchange });

    expect(screen.queryByRole("textbox")).toBeNull();

    await fireEvent.click(screen.getByTestId("chip-search"));
    expect(screen.getByRole("textbox")).toBeTruthy();

    await fireEvent.input(screen.getByRole("textbox"), { target: { value: "anger" } });
    await vi.advanceTimersByTimeAsync(500);
    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ search: "anger" }));
    vi.useRealTimers();
  });

  it("only offers genre/year/rating chips on the songs view", async () => {
    await renderMobile({ view: "artists" });

    expect(screen.queryByTestId("chip-genre")).toBeNull();
    expect(screen.queryByTestId("chip-year")).toBeNull();
    expect(screen.queryByTestId("chip-rating")).toBeNull();
    expect(screen.queryByTestId("chip-quality")).toBeNull();
    expect(screen.getByTestId("chip-role")).toBeTruthy();
  });
});
