import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { credentials } from "../../src/lib/store.js";
import { recordPlace, clearRecentPlaces } from "../../src/lib/recentPlaces.js";
import RecentPlacesRow from "../../src/lib/RecentPlacesRow.svelte";

describe("RecentPlacesRow", () => {
  beforeEach(() => {
    localStorage.clear();
    credentials.set({ url: "https://muma.test", username: "user", password: "pw" });
    clearRecentPlaces();
  });

  it("renders nothing when there are no recent places", () => {
    render(RecentPlacesRow, { onnavigate: vi.fn() });

    expect(screen.queryByText("Recent")).toBeNull();
  });

  it("renders nothing for an id-based place that never got a title", () => {
    recordPlace("artist:123");

    render(RecentPlacesRow, { onnavigate: vi.fn() });

    expect(screen.queryByText("Recent")).toBeNull();
  });

  it("lists titled places, most recent first, and taps navigate to them", async () => {
    recordPlace("genre:Hardcore", "Hardcore");
    recordPlace("label:Art of Creation", "Art of Creation");
    const onnavigate = vi.fn();

    render(RecentPlacesRow, { onnavigate });

    expect(screen.getByText("Recent")).toBeTruthy();
    const tiles = screen.getAllByRole("button").map((el) => el.textContent);
    expect(tiles[0]).toContain("Art of Creation");
    expect(tiles[1]).toContain("Hardcore");

    await fireEvent.click(screen.getByText("Art of Creation"));
    expect(onnavigate).toHaveBeenCalledWith("label:Art of Creation");
  });

  it("labels a place by its kind", () => {
    recordPlace("genre:Hardcore", "Hardcore");

    render(RecentPlacesRow, { onnavigate: vi.fn() });

    expect(screen.getByText("Genres")).toBeTruthy();
  });
});
