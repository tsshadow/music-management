import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/svelte";
import FavoritesView from "../../src/lib/FavoritesView.svelte";
import { normalizePreset } from "../../src/lib/presets.js";

/** Favorites owns its page layout while the shared grid still owns preset rendering. */
describe("FavoritesView", () => {
  it("places creation above a two-column preset grid and opens each preset", async () => {
    const onnavigate = vi.fn();
    render(FavoritesView, {
      onnavigate,
      canCreate: true,
      presets: [
        normalizePreset({ id: 1, name: "First mix" }),
        normalizePreset({ id: 2, name: "Second mix" }),
      ],
    });
    const page = screen.getByTestId("favorites-view");
    const grid = screen.getByTestId("preset-grid");
    expect(grid.parentElement).toHaveClass("grid-cols-2");
    expect(within(grid).getAllByRole("button")).toHaveLength(2);
    const buttons = within(page).getAllByRole("button");
    await fireEvent.click(buttons[0]);
    expect(onnavigate).toHaveBeenLastCalledWith("new-preset");
    await fireEvent.click(screen.getByText("First mix"));
    expect(onnavigate).toHaveBeenLastCalledWith("preset:1");
    await fireEvent.click(screen.getByText("Second mix"));
    expect(onnavigate).toHaveBeenLastCalledWith("preset:2");
  });

  it("offers creation on an empty account", async () => {
    const onnavigate = vi.fn();
    render(FavoritesView, { onnavigate, canCreate: true });
    await fireEvent.click(screen.getByRole("button"));
    expect(onnavigate).toHaveBeenCalledWith("new-preset");
  });

  it("keeps the existing account gate for preset creation", () => {
    render(FavoritesView, { onnavigate: vi.fn(), canCreate: false });
    expect(screen.queryByRole("button")).toBeNull();
  });
});
