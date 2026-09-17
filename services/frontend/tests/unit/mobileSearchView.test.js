import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import MobileSearchView from "../../src/lib/MobileSearchView.svelte";
import { viewMode } from "../../src/lib/store.js";

describe("MobileSearchView", () => {
  beforeEach(() => {
    viewMode.set("songs");
  });

  it("invites the listener to browse before they have typed anything", () => {
    render(MobileSearchView, { onnavigate: vi.fn() });

    expect(screen.getByText("Alles doorbladeren")).toBeTruthy();
  });

  it("renders the browse grid underneath the heading", () => {
    render(MobileSearchView, { onnavigate: vi.fn() });

    expect(screen.getByText("Genres")).toBeTruthy();
    expect(screen.getByText("Artiesten")).toBeTruthy();
  });

  // The advanced-search card used to sit above the grid; it moved to a filter icon beside
  // the search field in `TopBar.svelte`, so this screen opens straight on the category grid.
  it("no longer offers the advanced-search card", () => {
    render(MobileSearchView, { onnavigate: vi.fn() });

    expect(screen.queryByText("Geavanceerd zoeken")).toBeNull();
  });

  it("hands a tile tap straight up to the app", async () => {
    const onnavigate = vi.fn();
    render(MobileSearchView, { onnavigate });

    await fireEvent.click(screen.getByText("Albums"));

    expect(onnavigate).toHaveBeenCalledWith("albums");
  });

  it("offers no microphone when the platform has no speech recogniser", () => {
    render(MobileSearchView, {
      onnavigate: vi.fn(),
      platform: { speech: { supported: false } },
    });

    expect(screen.queryByLabelText("Microfoon")).toBeNull();
  });

  it("opens the voice screen from a microphone button when speech is supported", async () => {
    const onnavigate = vi.fn();
    render(MobileSearchView, {
      onnavigate,
      platform: { speech: { supported: true } },
    });

    await fireEvent.click(screen.getByLabelText("Microfoon"));

    expect(onnavigate).toHaveBeenCalledWith("voice");
  });
});
