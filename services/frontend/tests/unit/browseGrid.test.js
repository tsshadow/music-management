import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import BrowseGrid from "../../src/lib/BrowseGrid.svelte";
import { viewMode } from "../../src/lib/store.js";

describe("BrowseGrid", () => {
  beforeEach(() => {
    viewMode.set("songs");
  });

  it("offers a tile for every sidebar section that answers in song mode", () => {
    render(BrowseGrid, { onnavigate: vi.fn() });

    for (const label of [
      "Genres",
      "Labels",
      "Lineups",
      "Artiesten",
      "Albums",
      "Memories",
      "Geschiedenis",
      "Luisterstatistieken",
      "Favorieten",
    ]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  // The tagger only writes a FESTIVAL or PODCAST tag above the ten-minute
  // boundary song mode queries under, same as the sidebar's own library group.
  it.each(["Festivals", "Podcasts"])("leaves %s out of song mode", (label) => {
    render(BrowseGrid, { onnavigate: vi.fn() });

    expect(screen.queryByText(label)).toBeNull();
  });

  it.each(["Labels", "Lineups"])("leaves %s out of set mode", (label) => {
    viewMode.set("sets");
    render(BrowseGrid, { onnavigate: vi.fn() });

    expect(screen.queryByText(label)).toBeNull();
  });

  it("shows festivals and podcasts once in set mode", () => {
    viewMode.set("sets");
    render(BrowseGrid, { onnavigate: vi.fn() });

    expect(screen.getByText("Festivals")).toBeTruthy();
    expect(screen.getByText("Podcasts")).toBeTruthy();
  });

  it("navigates to the sidebar view a tile stands for", async () => {
    const onnavigate = vi.fn();
    render(BrowseGrid, { onnavigate });

    await fireEvent.click(screen.getByText("Genres"));

    expect(onnavigate).toHaveBeenCalledWith("genres");
  });
});

// The grid is the sidebar flattened: the mode's full list first, then playlists and
// the library group in the sidebar's order, with Downloads gated the same way.
it.each([true, false])(
  "tiles the sidebar in its own order and gates downloads (%s)",
  (supported) => {
    render(BrowseGrid, { onnavigate: vi.fn(), platform: { storage: { supported } } });
    const labels = screen.getAllByRole("button").map((button) => button.textContent.trim());
    expect(labels.slice(0, 4)).toEqual(["Nummers", "Afspeellijsten", "Artiesten", "Albums"]);
    expect(labels.includes("Downloads")).toBe(supported);
    expect(labels.slice(-5)).toEqual([
      "Favorieten",
      "Geschiedenis",
      "Memories",
      "Luisterstatistieken",
      "Wrapped",
    ]);
  },
);

it("offers the full list of the active mode as its first tile", async () => {
  viewMode.set("sets");
  const onnavigate = vi.fn();
  render(BrowseGrid, { onnavigate });

  const first = screen.getAllByRole("button")[0];
  expect(first.textContent.trim()).toBe("Sets");
  await fireEvent.click(first);

  expect(onnavigate).toHaveBeenCalledWith("sets");
});

it("opens playlists from a library tile", async () => {
  const onnavigate = vi.fn();
  render(BrowseGrid, { onnavigate });
  await fireEvent.click(screen.getByRole("button", { name: "Afspeellijsten" }));
  expect(onnavigate).toHaveBeenCalledWith("playlists");
});
