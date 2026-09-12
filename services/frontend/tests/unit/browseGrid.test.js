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
      "Luisteren",
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
