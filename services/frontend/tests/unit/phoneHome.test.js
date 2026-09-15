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
});
