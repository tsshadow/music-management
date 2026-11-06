import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import RadioView from "../../src/lib/RadioView.svelte";
import { registerRadioCommands } from "../../src/lib/radioCommands.js";
import { knownStations, liveStation, radioChannel } from "../../src/lib/store.js";
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
  });

  afterEach(() => {
    unregister();
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

  it("stops the row that plays", async () => {
    globalThis.fetch = radioApi();
    liveStation.set({ ...SLAM, title: null });
    render(RadioView);

    const row = await screen.findByRole("button", { name: "SLAM" });
    expect(row.getAttribute("aria-pressed")).toBe("true");
    await fireEvent.click(row);

    expect(commands.stop).toHaveBeenCalled();
    expect(commands.startStation).not.toHaveBeenCalled();
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
