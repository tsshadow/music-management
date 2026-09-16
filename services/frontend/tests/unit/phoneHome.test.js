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
  viewMode,
} from "../../src/lib/store.js";

// DailyMixesShelf (rendered when the daily-mix section is "Overzicht") builds its five cards
// from these two modules; stubbed here so a phone-home test never reaches MuMa for them.
vi.mock("../../src/lib/dailyMixes.js", () => ({
  loadDailyMixCards: async () => [],
}));
vi.mock("../../src/lib/genreTints.js", () => ({
  fetchGenreTints: async () => ({}),
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
