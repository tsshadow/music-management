import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import CollectionGrid from "../../src/lib/CollectionGrid.svelte";
import { defaultCollectionState } from "../../src/lib/collections.js";

const ITEMS = [
  { value: "Hardcore", songCount: 1200, albumCount: 40 },
  { value: "Uptempo", songCount: 400, albumCount: 12 },
];

function renderGrid(props = {}) {
  return render(CollectionGrid, {
    type: "genres",
    title: "Genres",
    items: ITEMS,
    state: defaultCollectionState("genres"),
    emptyText: "Nothing here",
    onselect: vi.fn(),
    ...props,
  });
}

describe("CollectionGrid", () => {
  it("renders a card per item with its track count", () => {
    renderGrid();

    expect(screen.getByText("Hardcore")).toBeTruthy();
    expect(screen.getByText("Uptempo")).toBeTruthy();
  });

  it("calls onselect with the item that was clicked", async () => {
    const onselect = vi.fn();
    renderGrid({ onselect });

    await fireEvent.click(screen.getByText("Hardcore"));

    expect(onselect).toHaveBeenCalledWith(ITEMS[0]);
  });

  it("opens a card from the keyboard as well as the mouse", async () => {
    const onselect = vi.fn();
    renderGrid({ onselect });

    await fireEvent.keyDown(screen.getByText("Uptempo").closest('[role="button"]'), {
      key: "Enter",
    });

    expect(onselect).toHaveBeenCalledWith(ITEMS[1]);
  });

  it("shows the empty text when the server returned nothing", () => {
    renderGrid({ items: [] });

    expect(screen.getByText("Nothing here")).toBeTruthy();
  });

  it("shows the hint line under the empty text when one is given", () => {
    renderGrid({ items: [], emptyHint: "FESTIVAL is not indexed" });

    expect(screen.getByText("FESTIVAL is not indexed")).toBeTruthy();
  });

  it("offers to clear the filters when a search matched nothing", () => {
    renderGrid({ state: { ...defaultCollectionState("genres"), search: "zzzz" } });

    expect(screen.getByText("Niets voldoet aan deze filters")).toBeTruthy();
    expect(screen.getByText("Filters wissen")).toBeTruthy();
  });

  it("renders no favourite star when the collection has no favourites", () => {
    renderGrid({ onfavorite: null });

    expect(screen.queryByLabelText("Favoriet toggelen")).toBeNull();
  });

  it("reports a favourite toggle without also opening the card", async () => {
    const onfavorite = vi.fn();
    const onselect = vi.fn();
    renderGrid({ onfavorite, onselect, favorites: [] });

    await fireEvent.click(screen.getAllByLabelText("Favoriet toggelen")[0]);

    expect(onfavorite).toHaveBeenCalledWith("Hardcore");
    expect(onselect).not.toHaveBeenCalled();
  });

  it("lets a collection name its own favourite control", () => {
    renderGrid({ onfavorite: vi.fn(), favoriteAriaLabel: "Favoriet label toggelen" });

    expect(screen.getAllByLabelText("Favoriet label toggelen").length).toBe(2);
  });

  it("leaves a countless collection without a count line", () => {
    renderGrid({
      type: "lineups",
      title: "Lineups",
      items: [{ value: "Defqon.1 2025" }],
      state: defaultCollectionState("lineups"),
    });

    expect(screen.getByText("Defqon.1 2025")).toBeTruthy();
    expect(screen.queryByText(/nummers/)).toBeNull();
  });
});
