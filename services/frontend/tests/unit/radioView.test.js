import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/svelte";
import { get } from "svelte/store";
import RadioView from "../../src/lib/RadioView.svelte";
import { registerRadioCommands } from "../../src/lib/radioCommands.js";
import {
  favoriteStations,
  knownStations,
  liveStation,
  radioChannel,
  recentStations,
} from "../../src/lib/store.js";
import { browseSections } from "../../src/lib/navigation.js";
import { TILE_COLORS } from "../../src/lib/browseColors.js";

const SLAM = { slug: "slam", name: "SLAM", stream_url: "https://example.com/slam.mp3" };
const MAIN = { slug: "main", name: "MuMa Radio", filter: {} };

/**
 * An API that answers the two lists, or fails for the ones named.
 *
 * @param {{stations?: boolean, channels?: boolean}} [broken]
 */
function radioApi(broken = {}) {
  return vi.fn(async (url) => {
    if (url.includes("/stations")) {
      return broken.stations
        ? { ok: false, status: 500 }
        : { ok: true, json: async () => ({ stations: [SLAM] }) };
    }
    return broken.channels
      ? { ok: false, status: 500 }
      : { ok: true, json: async () => ({ channels: [MAIN] }) };
  });
}

describe("RadioView", () => {
  let commands;
  let unregister;

  beforeEach(() => {
    commands = { startRadio: vi.fn(), startStation: vi.fn(), stop: vi.fn() };
    unregister = registerRadioCommands(commands);
    liveStation.set(null);
    radioChannel.set(null);
    knownStations.set([]);
    favoriteStations.set([]);
    recentStations.set([]);
  });

  afterEach(() => {
    unregister();
    favoriteStations.set([]);
    recentStations.set([]);
    liveStation.set(null);
    radioChannel.set(null);
  });

  it("lists stations and channels under their own heading, and remembers the stations", async () => {
    globalThis.fetch = radioApi();
    render(RadioView);

    expect(await screen.findByText("SLAM")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "MuMa Radio" })).toBeTruthy();
    expect(get(knownStations)).toEqual([SLAM]);
    expect(commands.startStation).not.toHaveBeenCalled();
  });

  it("starts the row that is tapped", async () => {
    globalThis.fetch = radioApi();
    render(RadioView);

    await fireEvent.click(await screen.findByText("SLAM"));
    expect(commands.startStation).toHaveBeenCalledWith(SLAM);

    await fireEvent.click(screen.getByRole("button", { name: /MuMa Radio/ }));
    expect(commands.startRadio).toHaveBeenCalledWith(MAIN);
  });

  it("stops the station that plays", async () => {
    globalThis.fetch = radioApi();
    liveStation.set({ ...SLAM, title: null });
    render(RadioView);

    const tile = await screen.findByRole("button", { name: "SLAM" });
    expect(tile.getAttribute("aria-pressed")).toBe("true");
    await fireEvent.click(tile);

    expect(commands.stop).toHaveBeenCalled();
    expect(commands.startStation).not.toHaveBeenCalled();
  });

  it("shows the logo, and the name when the station has no logo file", async () => {
    globalThis.fetch = radioApi();
    const { container } = render(RadioView);
    await screen.findByText("SLAM");

    const logo = container.querySelector("img");
    expect(logo.getAttribute("src")).toBe("/images/stations/slam.png");

    await fireEvent.error(logo);
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getAllByText("SLAM")).toHaveLength(2);
  });

  it("marks a favorite with the star, without starting the station", async () => {
    globalThis.fetch = radioApi();
    render(RadioView);

    await fireEvent.click(
      await screen.findByRole("button", { name: "SLAM toevoegen aan favorieten" }),
    );

    expect(get(favoriteStations)).toEqual(["slam"]);
    expect(within(screen.getByTestId("stations-favorites")).getByText("SLAM")).toBeTruthy();
    expect(commands.startStation).not.toHaveBeenCalled();
  });

  it("shows the stations played last in their own section", async () => {
    globalThis.fetch = radioApi();
    recentStations.set(["slam"]);
    render(RadioView);

    expect(within(await screen.findByTestId("stations-recent")).getByText("SLAM")).toBeTruthy();
  });

  it("has no favorite or recent section when both are empty", async () => {
    globalThis.fetch = radioApi();
    render(RadioView);

    await screen.findByTestId("stations-all");
    expect(screen.queryByTestId("stations-favorites")).toBeNull();
    expect(screen.queryByTestId("stations-recent")).toBeNull();
  });

  it("has a search box from twelve stations, which narrows the list", async () => {
    const many = Array.from({ length: 12 }, (_, i) => ({ slug: `s${i}`, name: `Zender ${i}` }));
    many[3] = SLAM;
    globalThis.fetch = vi.fn(async (url) => ({
      ok: true,
      json: async () => (url.includes("/stations") ? { stations: many } : { channels: [] }),
    }));
    render(RadioView);

    const search = await screen.findByTestId("station-search");
    await fireEvent.input(search, { target: { value: "sla" } });

    expect(within(screen.getByTestId("stations-all")).getAllByTestId("station-tile")).toHaveLength(
      1,
    );

    await fireEvent.input(search, { target: { value: "bestaat niet" } });
    expect(screen.queryByTestId("stations-all")).toBeNull();
    expect(screen.getByText("Geen zender gevonden")).toBeTruthy();
  });

  it("has no search box for a short list", async () => {
    globalThis.fetch = radioApi();
    render(RadioView);

    await screen.findByTestId("stations-all");
    expect(screen.queryByTestId("station-search")).toBeNull();
  });

  it("still shows the channels when the stations do not load", async () => {
    globalThis.fetch = radioApi({ stations: true });
    render(RadioView);

    await screen.findByRole("button", { name: /MuMa Radio/ });
    expect(screen.queryByText("SLAM")).toBeNull();
  });

  it("says so when neither list loads", async () => {
    globalThis.fetch = radioApi({ stations: true, channels: true });
    render(RadioView);

    await waitFor(() => expect(screen.getByText("Kon de radiolijst niet laden")).toBeTruthy());
  });

  it("has a tile under Browse in both modes, with its own colour", () => {
    for (const mode of ["songs", "sets"]) {
      expect(browseSections(mode, {}).map((section) => section.id)).toContain("radio");
    }
    expect(TILE_COLORS.radio).toBeTruthy();
  });
});
