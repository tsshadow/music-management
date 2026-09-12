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

  it("hands a tile tap straight up to the app", async () => {
    const onnavigate = vi.fn();
    render(MobileSearchView, { onnavigate });

    await fireEvent.click(screen.getByText("Albums"));

    expect(onnavigate).toHaveBeenCalledWith("albums");
  });
});
