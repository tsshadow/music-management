import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/svelte";
import CollectionBar from "../../src/lib/CollectionBar.svelte";
import { isMobile } from "../../src/lib/store.js";
import { defaultCollectionState, PLAYLIST_VISIBILITY } from "../../src/lib/collections.js";

describe("CollectionBar phone chips", () => {
  beforeEach(() => {
    isMobile.set(true);
  });

  afterEach(() => {
    isMobile.set(false);
  });

  function renderPlaylists(props = {}) {
    return render(CollectionBar, {
      type: "playlists",
      state: defaultCollectionState("playlists"),
      total: 296,
      shown: 296,
      favoriteCount: 3,
      visibilityOptions: PLAYLIST_VISIBILITY,
      onchange: vi.fn(),
      ...props,
    });
  }

  it("folds the count into a section line instead of a loose number", async () => {
    renderPlaylists();

    expect(screen.getByTestId("mobile-collection-count").textContent.trim()).toBe(
      "296 Afspeellijsten",
    );
  });

  it("shows the shown/total form when a filter narrows the grid", async () => {
    renderPlaylists({ shown: 12 });

    expect(screen.getByTestId("mobile-collection-count").textContent).toContain("12 van 296");
  });

  it("keeps the visibility chips in one scrollable row", async () => {
    renderPlaylists();

    const row = screen.getByTestId("mobile-collection-chips");
    expect(within(row).getByText("Van mij")).toBeTruthy();
    expect(within(row).getByText("Openbaar")).toBeTruthy();
    expect(within(row).getByText("Privé")).toBeTruthy();
  });

  it("opens the sort sheet with a field and a direction, and reports a pick", async () => {
    const onchange = vi.fn();
    const state = defaultCollectionState("playlists");
    renderPlaylists({ state, onchange });

    await fireEvent.click(screen.getByTestId("chip-sort"));
    const sheet = await screen.findByTestId("bottom-sheet");

    expect(within(sheet).getByText("Oplopend")).toBeTruthy();
    expect(within(sheet).getByText("Aflopend")).toBeTruthy();

    await fireEvent.click(within(sheet).getByText("Aantal nummers"));

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ sort: "songs" }));
    await waitFor(() => expect(screen.queryByTestId("bottom-sheet")).toBeNull());
  });

  it("picks a direction from the same sheet", async () => {
    const onchange = vi.fn();
    const state = defaultCollectionState("playlists");
    renderPlaylists({ state, onchange });

    await fireEvent.click(screen.getByTestId("chip-sort"));
    const sheet = await screen.findByTestId("bottom-sheet");
    await fireEvent.click(within(sheet).getByText("Aflopend"));

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ direction: "desc" }));
  });

  it("toggles the favorites chip", async () => {
    const onchange = vi.fn();
    const state = defaultCollectionState("playlists");
    renderPlaylists({ state, onchange });

    await fireEvent.click(screen.getByText("Favorieten (3)"));

    expect(onchange).toHaveBeenCalledWith(expect.objectContaining({ favoritesOnly: true }));
  });

  it("expands the search chip into an input", async () => {
    const onchange = vi.fn();
    vi.useFakeTimers();
    const state = defaultCollectionState("playlists");
    renderPlaylists({ state, onchange });

    expect(screen.queryByRole("textbox")).toBeNull();
    await fireEvent.click(screen.getByTestId("chip-search"));

    await fireEvent.input(screen.getByRole("textbox"), { target: { value: "workout" } });
    await vi.advanceTimersByTimeAsync(300);

    expect(state.search).toBe("workout");
    expect(onchange).toHaveBeenCalled();
    vi.useRealTimers();
  });
});
