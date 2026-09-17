import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/svelte";
import PhoneHome from "../../src/lib/PhoneHome.svelte";
import {
  memoriesOnHomeEnabled,
  homeModeReleaseRadar,
  homeModeDailyMix,
  homeModeFavorites,
  homeModeRecentlyReleased,
  homeModeRecentlyAdded,
  credentials,
  mumaApiKey,
  viewMode,
} from "../../src/lib/store.js";
import { loadTopArtists, loadTopLabels, resolveArtistView } from "../../src/lib/homeRankings.js";

// DailyMixesShelf (rendered when the daily-mix section is "Overzicht") builds its five cards
// from these two modules; stubbed here so a phone-home test never reaches MuMa for them.
vi.mock("../../src/lib/dailyMixes.js", () => ({
  loadDailyMixCards: async () => [],
}));
vi.mock("../../src/lib/genreTints.js", () => ({
  fetchGenreTints: async () => ({}),
}));
// The ranking rows are network calls in their own right (see homeRankings.test.js for those);
// here only the wiring -- fetched on the right condition, rendered, tapped -- is under test.
vi.mock("../../src/lib/homeRankings.js", () => ({
  loadTopArtists: vi.fn(async () => []),
  loadTopLabels: vi.fn(async () => []),
  resolveArtistView: vi.fn(async () => null),
}));

/** Each account mode controls placement, independent of whether a source is empty. */
describe("phone home modes", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "", password: "" });
    memoriesOnHomeEnabled.set(true);
    homeModeReleaseRadar.set("BUTTON");
    homeModeDailyMix.set("BUTTON");
    homeModeFavorites.set("OFF");
    homeModeRecentlyReleased.set("OFF");
    homeModeRecentlyAdded.set("OFF");
  });

  it("keeps section tiles on Home without the preset grid", async () => {
    const onnavigate = vi.fn();
    render(PhoneHome, { onnavigate, memoryGroups: [{ year: 2024, songs: [{ id: "1" }] }] });
    const grid = within(screen.getByTestId("home-quick-access"));
    expect(grid.getAllByRole("button")).toHaveLength(3);
    await fireEvent.click(grid.getByText("Memories"));
    expect(onnavigate).toHaveBeenLastCalledWith("memories");
    expect(screen.queryByTestId("preset-grid")).toBeNull();
  });

  it("moves overview modes below the grid and hides off modes", () => {
    memoriesOnHomeEnabled.set(false);
    homeModeReleaseRadar.set("OFF");
    homeModeDailyMix.set("OVERVIEW");
    homeModeFavorites.set("OVERVIEW");
    homeModeRecentlyReleased.set("OVERVIEW");
    homeModeRecentlyAdded.set("BUTTON");
    render(PhoneHome, { onnavigate: vi.fn() });
    expect(within(screen.getByTestId("home-quick-access")).getAllByRole("button")).toHaveLength(1);
    expect(screen.queryByText("Release Radar")).toBeNull();
    expect(screen.getAllByRole("heading", { level: 2 })).toHaveLength(3);
  });
  it("loads real release and addition order for the current mode", async () => {
    credentials.set({ url: "https://lms.example", username: "test", password: "test" });
    viewMode.set("sets");
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": { tracks: { track: [] }, starred2: { song: [] } },
      }),
    }));
    render(PhoneHome, { onnavigate: vi.fn() });
    await vi.waitFor(() => expect(globalThis.fetch).toHaveBeenCalledTimes(3));
    const queries = globalThis.fetch.mock.calls.map(([url]) => new URL(url));
    const recent = queries.filter((url) => url.pathname.endsWith("getSpotifyTracks"));
    expect(recent.map((url) => url.searchParams.get("sort"))).toEqual(["recent", "added"]);
    expect(recent.every((url) => url.searchParams.get("minDuration") === "10")).toBe(true);
  });
  it("keeps addition order when opening the full list", async () => {
    homeModeRecentlyAdded.set("BUTTON");
    const onrecent = vi.fn();
    render(PhoneHome, { onnavigate: vi.fn(), onrecent });
    await fireEvent.click(screen.getByText("Recent toegevoegd"));
    expect(onrecent).toHaveBeenCalledWith("added");
  });

  it("opens the daily mixes page from its own tile, not a single feed", async () => {
    const onnavigate = vi.fn();
    render(PhoneHome, { onnavigate });

    await fireEvent.click(screen.getByText("Dagelijkse mixen"));

    expect(onnavigate).toHaveBeenCalledWith("daily-mixes");
  });

  it("shows the daily mixes shelf, not a track shelf, in Overzicht mode", () => {
    homeModeReleaseRadar.set("OFF");
    homeModeDailyMix.set("OVERVIEW");

    render(PhoneHome, { onnavigate: vi.fn() });

    expect(screen.getByRole("heading", { name: "Dagelijkse mixen" })).toBeTruthy();
  });

  it("shows nothing for the daily mixes section when its mode is off", () => {
    homeModeDailyMix.set("OFF");

    render(PhoneHome, { onnavigate: vi.fn() });

    expect(screen.queryByText("Dagelijkse mixen")).toBeNull();
  });
});

// A tile with nothing to show is not "broken" -- it is a destination that has not answered
// yet, and each one gets a line explaining what it is for instead of a generic "no tracks".
describe("phone home empty, loading and failed copy", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "", password: "" });
    memoriesOnHomeEnabled.set(false);
    homeModeReleaseRadar.set("BUTTON");
    homeModeDailyMix.set("OFF");
    homeModeFavorites.set("BUTTON");
    homeModeRecentlyReleased.set("BUTTON");
    homeModeRecentlyAdded.set("BUTTON");
  });

  it("shows the destination's own copy for an empty tile, not the generic line", async () => {
    render(PhoneHome, { onnavigate: vi.fn() });

    expect(await screen.findByText("Ontdek nieuwe releases")).toBeTruthy();
    expect(await screen.findByText("Nog niets met een ster")).toBeTruthy();
    expect(await screen.findByText("De nieuwste releases in je bibliotheek")).toBeTruthy();
    expect(await screen.findByText("Wat er net is bijgekomen")).toBeTruthy();
  });

  it("shows the failed copy when the favourites request breaks", async () => {
    credentials.set({ url: "https://lms.example", username: "test", password: "test" });
    globalThis.fetch = vi.fn(async (url) => {
      if (String(url).includes("getStarred2")) throw new Error("network down");
      return { ok: true, json: async () => ({ "subsonic-response": { tracks: { track: [] } } }) };
    });

    render(PhoneHome, { onnavigate: vi.fn() });

    expect(await screen.findByText("Kon niet laden")).toBeTruthy();
  });

  it("marks a feed section from Dashboard as failed via its own subtitle", async () => {
    render(PhoneHome, {
      onnavigate: vi.fn(),
      sections: [{ id: "feed:release-radar", tracks: [], failed: true }],
    });

    expect(await screen.findByText("Kon niet laden")).toBeTruthy();
  });
});

describe("phone home quick-access tile count", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "", password: "" });
    memoriesOnHomeEnabled.set(true);
    homeModeReleaseRadar.set("BUTTON");
    homeModeDailyMix.set("BUTTON");
    homeModeFavorites.set("OFF");
    homeModeRecentlyReleased.set("OFF");
    homeModeRecentlyAdded.set("OFF");
  });

  it("stretches the last tile across the row when the count is odd", () => {
    // Memories + release radar + daily mixes: three tiles, an orphan half-row without this.
    render(PhoneHome, { onnavigate: vi.fn() });

    const grid = within(screen.getByTestId("home-quick-access"));
    const buttons = grid.getAllByRole("button");
    expect(buttons).toHaveLength(3);
    expect(buttons.at(-1).className).toContain("col-span-2");
    expect(buttons[0].className).not.toContain("col-span-2");
    expect(buttons[1].className).not.toContain("col-span-2");
  });

  it("leaves every tile at its normal width when the count is even", () => {
    homeModeFavorites.set("BUTTON");

    render(PhoneHome, { onnavigate: vi.fn() });

    const grid = within(screen.getByTestId("home-quick-access"));
    const buttons = grid.getAllByRole("button");
    expect(buttons).toHaveLength(4);
    for (const button of buttons) expect(button.className).not.toContain("col-span-2");
  });
});

// PhoneHome's own recent shelves show compact rows, not another grid of mostly-placeholder
// cards -- see `HomeShelf.svelte`'s `layout="rows"`.
describe("phone home recent shelves", () => {
  it("renders the recently released and recently added shelves as rows", async () => {
    credentials.set({ url: "https://lms.example", username: "test", password: "test" });
    memoriesOnHomeEnabled.set(false);
    homeModeReleaseRadar.set("OFF");
    homeModeDailyMix.set("OFF");
    homeModeFavorites.set("OFF");
    homeModeRecentlyReleased.set("OVERVIEW");
    homeModeRecentlyAdded.set("OVERVIEW");
    globalThis.fetch = vi.fn(async (url) => {
      const parsed = new URL(url);
      const sort = parsed.searchParams.get("sort");
      const track = { id: `song-${sort}`, title: `Track ${sort}`, artist: "Angerfist" };
      return {
        ok: true,
        json: async () => ({ "subsonic-response": { tracks: { track: [track] } } }),
      };
    });

    render(PhoneHome, { onnavigate: vi.fn() });

    await vi.waitFor(() => expect(screen.getAllByTestId("track-row-compact")).toHaveLength(2));
  });
});

// Below the destination shelves, Home shows one tile per memories year -- reusing the same
// `MemoryYearCard` the full Memories page renders in a grid.
describe("phone home memories row", () => {
  const groups = [
    { year: 2016, yearsAgo: 8, exact: true, songs: [{ id: "s1", title: "Track A" }] },
    { year: 2018, yearsAgo: 6, exact: false, songs: [{ id: "s2", title: "Track B" }] },
  ];

  beforeEach(() => {
    credentials.set({ url: "", username: "", password: "" });
    homeModeReleaseRadar.set("OFF");
    homeModeDailyMix.set("OFF");
    homeModeFavorites.set("OFF");
    homeModeRecentlyReleased.set("OFF");
    homeModeRecentlyAdded.set("OFF");
  });

  it("renders one card per year and opens that year on tap", async () => {
    memoriesOnHomeEnabled.set(true);
    const onnavigate = vi.fn();
    render(PhoneHome, { onnavigate, memoryGroups: groups });

    const row = within(screen.getByTestId("home-memories-row"));
    expect(row.getAllByRole("button", { name: /openen$/ })).toHaveLength(2);

    await fireEvent.click(screen.getByRole("button", { name: "2016 openen" }));
    expect(onnavigate).toHaveBeenCalledWith("memories:2016");
  });

  it("is hidden when memories on Home is disabled", () => {
    memoriesOnHomeEnabled.set(false);
    render(PhoneHome, { onnavigate: vi.fn(), memoryGroups: groups });
    expect(screen.queryByTestId("home-memories-row")).toBeNull();
  });

  it("is hidden when there are no memory groups", () => {
    memoriesOnHomeEnabled.set(true);
    render(PhoneHome, { onnavigate: vi.fn(), memoryGroups: [] });
    expect(screen.queryByTestId("home-memories-row")).toBeNull();
  });
});

// Songs and sets each fall back to one "recent" shelf when neither of their two destinations is
// already set to draw a shelf of its own, so Home always has something to play beneath the tiles.
describe("phone home fallback recent shelf", () => {
  beforeEach(() => {
    memoriesOnHomeEnabled.set(false);
    homeModeReleaseRadar.set("OFF");
    homeModeDailyMix.set("OFF");
    homeModeFavorites.set("OFF");
    credentials.set({ url: "https://lms.example", username: "test", password: "test" });
    globalThis.fetch = vi.fn(async (url) => {
      const parsed = new URL(url);
      const sort = parsed.searchParams.get("sort");
      const track = { id: `song-${sort}`, title: `Track ${sort}`, artist: "Angerfist" };
      return {
        ok: true,
        json: async () => ({ "subsonic-response": { tracks: { track: [track] } } }),
      };
    });
  });

  it("shows recently added in songs mode when both recent destinations are tiles", async () => {
    viewMode.set("songs");
    homeModeRecentlyReleased.set("BUTTON");
    homeModeRecentlyAdded.set("BUTTON");
    render(PhoneHome, { onnavigate: vi.fn() });

    await vi.waitFor(() => expect(screen.getAllByTestId("track-row-compact")).toHaveLength(1));
    expect(screen.getByRole("heading", { name: "Recent toegevoegd" })).toBeTruthy();
  });

  it("shows recently released in sets mode when both recent destinations are tiles", async () => {
    viewMode.set("sets");
    homeModeRecentlyReleased.set("BUTTON");
    homeModeRecentlyAdded.set("BUTTON");
    render(PhoneHome, { onnavigate: vi.fn() });

    await vi.waitFor(() => expect(screen.getAllByTestId("track-row-compact")).toHaveLength(1));
    expect(screen.getByRole("heading", { name: "Recent uitgebracht" })).toBeTruthy();
  });

  it("does not duplicate the shelf when recently-added already renders as its own overview shelf", async () => {
    viewMode.set("songs");
    homeModeRecentlyAdded.set("OVERVIEW");
    homeModeRecentlyReleased.set("BUTTON");
    render(PhoneHome, { onnavigate: vi.fn() });

    await vi.waitFor(() => expect(screen.getAllByTestId("track-row-compact")).toHaveLength(1));
    expect(screen.getAllByRole("heading", { name: "Recent toegevoegd" })).toHaveLength(1);
  });
});

// The two ranking strips below the fallback shelf: "Jouw artiesten deze maand" and "Jouw
// labels", drawn from /api/listening (mocked at the module level above) and gated on the
// MuMa key rather than the Subsonic credentials every other section here uses.
describe("phone home ranking rows", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    loadTopArtists.mockResolvedValue([]);
    loadTopLabels.mockResolvedValue([]);
    resolveArtistView.mockResolvedValue(null);
    credentials.set({ url: "", username: "", password: "" });
    mumaApiKey.set("");
    memoriesOnHomeEnabled.set(false);
    homeModeReleaseRadar.set("OFF");
    homeModeDailyMix.set("OFF");
    homeModeFavorites.set("OFF");
    homeModeRecentlyReleased.set("OFF");
    homeModeRecentlyAdded.set("OFF");
  });

  it("never asks MuMa for a ranking when the account has no MuMa key", () => {
    render(PhoneHome, { onnavigate: vi.fn() });

    expect(loadTopArtists).not.toHaveBeenCalled();
    expect(loadTopLabels).not.toHaveBeenCalled();
    expect(screen.queryByText("Jouw artiesten deze maand")).toBeNull();
    expect(screen.queryByText("Jouw labels")).toBeNull();
  });

  it("hides both rows when the key is set but neither ranking has anything", async () => {
    mumaApiKey.set("secret");
    render(PhoneHome, { onnavigate: vi.fn() });

    await vi.waitFor(() => expect(loadTopArtists).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Jouw artiesten deze maand")).toBeNull();
    expect(screen.queryByText("Jouw labels")).toBeNull();
  });

  it("renders one tile per artist and label the loaders return", async () => {
    mumaApiKey.set("secret");
    loadTopArtists.mockResolvedValue([{ name: "Angerfist", listens: 12 }]);
    loadTopLabels.mockResolvedValue([{ name: "Art of Creation", listens: 5 }]);

    render(PhoneHome, { onnavigate: vi.fn() });

    expect(await screen.findByText("Jouw artiesten deze maand")).toBeTruthy();
    expect(screen.getByText("Angerfist")).toBeTruthy();
    expect(screen.getByText("Jouw labels")).toBeTruthy();
    expect(screen.getByText("Art of Creation")).toBeTruthy();
    expect(screen.getAllByText(/keer geluisterd/).length).toBeGreaterThan(0);
  });

  it("resolves an artist tap to its LMS view before navigating", async () => {
    mumaApiKey.set("secret");
    loadTopArtists.mockResolvedValue([{ name: "Angerfist", listens: 12 }]);
    resolveArtistView.mockResolvedValue("artist:99");
    const onnavigate = vi.fn();

    render(PhoneHome, { onnavigate });
    await fireEvent.click(await screen.findByText("Angerfist"));

    expect(resolveArtistView).toHaveBeenCalledWith("Angerfist");
    await vi.waitFor(() => expect(onnavigate).toHaveBeenCalledWith("artist:99"));
  });

  it("falls back to a search view when the artist name does not resolve", async () => {
    mumaApiKey.set("secret");
    loadTopArtists.mockResolvedValue([{ name: "Unknown Artist", listens: 3 }]);
    resolveArtistView.mockResolvedValue(null);
    const onnavigate = vi.fn();

    render(PhoneHome, { onnavigate });
    await fireEvent.click(await screen.findByText("Unknown Artist"));

    await vi.waitFor(() => expect(onnavigate).toHaveBeenCalledWith("search:Unknown Artist"));
  });

  it("navigates a label tap straight to label:<name>, no resolution involved", async () => {
    mumaApiKey.set("secret");
    loadTopLabels.mockResolvedValue([{ name: "Art of Creation", listens: 5 }]);
    const onnavigate = vi.fn();

    render(PhoneHome, { onnavigate });
    await fireEvent.click(await screen.findByText("Art of Creation"));

    expect(onnavigate).toHaveBeenCalledWith("label:Art of Creation");
    expect(resolveArtistView).not.toHaveBeenCalled();
  });

  it('opens the listening stats page from a row\'s own "show all"', async () => {
    mumaApiKey.set("secret");
    loadTopArtists.mockResolvedValue([{ name: "Angerfist", listens: 12 }]);
    const onnavigate = vi.fn();

    render(PhoneHome, { onnavigate });
    await screen.findByText("Jouw artiesten deze maand");
    const artistsRow = within(screen.getByTestId("home-top-artists"));
    await fireEvent.click(artistsRow.getByText("Alles tonen"));

    expect(onnavigate).toHaveBeenCalledWith("listening");
  });
});
