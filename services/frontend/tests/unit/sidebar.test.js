import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import Sidebar from "../../src/lib/Sidebar.svelte";
import { credentials, favoriteGenres, viewMode } from "../../src/lib/store.js";

const GENRES = [
  { value: "Hardcore", songCount: 1200 },
  { value: "Uptempo", songCount: 400 },
  { value: "Obscure", songCount: 2 },
];

function subsonic(genres = GENRES) {
  return vi.fn(async () => ({
    ok: true,
    json: async () => ({ "subsonic-response": { status: "ok", genres: { genre: genres } } }),
  }));
}

async function renderLoaded(props = {}) {
  const rendered = render(Sidebar, { activeView: "home", onnavigate: vi.fn(), ...props });
  await waitFor(() => expect(screen.getByText("Hardcore")).toBeTruthy());
  return rendered;
}

async function openLibrary() {
  await fireEvent.click(screen.getByText("Bibliotheek"));
}

describe("Sidebar", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    viewMode.set("songs");
    favoriteGenres.set([]);
    localStorage.clear();
    globalThis.fetch = subsonic();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists the genres the library has", async () => {
    await renderLoaded();

    expect(screen.getByText("Uptempo")).toBeTruthy();
  });

  it("leaves out genres with almost nothing in them", async () => {
    await renderLoaded();

    expect(screen.queryByText("Obscure")).toBeNull();
  });

  it("shows only the favourites once some are marked", async () => {
    favoriteGenres.set(["Uptempo"]);

    render(Sidebar, { activeView: "home", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Uptempo")).toBeTruthy());
    expect(screen.queryByText("Hardcore")).toBeNull();
  });

  it("navigating to a genre is reported to the parent", async () => {
    const onnavigate = vi.fn();
    await renderLoaded({ onnavigate });

    await fireEvent.click(screen.getByText("Hardcore"));

    expect(onnavigate).toHaveBeenCalledWith("genre:Hardcore");
  });

  it("navigating to a section is reported to the parent", async () => {
    const onnavigate = vi.fn();
    await renderLoaded({ onnavigate });
    await openLibrary();

    await fireEvent.click(screen.getByText("Albums"));

    expect(onnavigate).toHaveBeenCalledWith("albums");
  });

  it("keeps the library sections out of the way until asked", async () => {
    await renderLoaded();

    expect(screen.queryByText("Albums")).toBeNull();
    expect(screen.queryByText("Artiesten")).toBeNull();
  });

  it("reveals every library section at once", async () => {
    await renderLoaded();

    await openLibrary();

    for (const label of ["Artiesten", "Albums", "Genres", "Labels"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it("folds the library away again on a second click", async () => {
    await renderLoaded();
    await openLibrary();

    await openLibrary();

    expect(screen.queryByText("Albums")).toBeNull();
  });

  it("remembers that the library was left open", async () => {
    const { unmount } = await renderLoaded();
    await openLibrary();
    unmount();

    render(Sidebar, { activeView: "home", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Albums")).toBeTruthy());
  });

  it("opens the library when the current view lives inside it", async () => {
    await renderLoaded({ activeView: "labels" });

    expect(screen.getByText("Labels")).toBeTruthy();
  });

  it("no longer offers the release radar", async () => {
    await renderLoaded();

    expect(screen.queryByText("Release Radar")).toBeNull();
  });

  it("keeps the songs list reachable next to the mode switch", async () => {
    const onnavigate = vi.fn();
    await renderLoaded({ onnavigate });

    await fireEvent.click(screen.getAllByText("Nummers")[1]);

    expect(onnavigate).toHaveBeenCalledWith("songs");
    expect(get(viewMode)).toBe("songs");
  });

  it("switching to sets changes the mode", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText("Sets"));

    expect(get(viewMode)).toBe("sets");
  });

  it("switching back to songs changes the mode", async () => {
    viewMode.set("sets");
    await renderLoaded();

    await fireEvent.click(screen.getByText("Nummers"));

    expect(get(viewMode)).toBe("songs");
  });

  it("survives a genre list that fails to load", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });

    render(Sidebar, { activeView: "home", onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Bibliotheek")).toBeTruthy());
  });

  it("copes with a server that returns a single genre rather than a list", async () => {
    globalThis.fetch = subsonic({ value: "Hardcore", songCount: 1200 });

    await renderLoaded();

    expect(screen.getByText("Hardcore")).toBeTruthy();
  });

  it("offers the tag-driven browse pages that song mode can answer", async () => {
    await renderLoaded();
    await openLibrary();

    expect(screen.getByText("Jaren")).toBeTruthy();
    expect(screen.getByText("Lineups")).toBeTruthy();
  });

  // The tagger writes a FESTIVAL or PODCAST tag only above ten minutes, the same
  // threshold song mode queries under, so these two lists cannot answer there.
  it.each(["Festivals", "Podcasts"])("leaves %s out of song mode", async (label) => {
    await renderLoaded();
    await openLibrary();

    expect(screen.queryByText(label)).toBeNull();
  });

  it.each(["Labels", "Lineups"])("leaves %s out of set mode", async (label) => {
    viewMode.set("sets");
    await renderLoaded();
    await openLibrary();

    expect(screen.queryByText(label)).toBeNull();
  });

  it("navigates to the festivals page when it is picked", async () => {
    viewMode.set("sets");
    const onnavigate = vi.fn();
    await renderLoaded({ onnavigate });
    await openLibrary();

    await fireEvent.click(screen.getByText("Festivals"));

    expect(onnavigate).toHaveBeenCalledWith("festivals");
  });

  // libraryExpanded derives from libraryItems.some(item => item.id === activeView), so a
  // page that lives in the group but is missing from that list renders collapsed on a
  // deep link.
  it("keeps the library group open when the app lands straight on a lineup page", async () => {
    await renderLoaded({ activeView: "lineups" });

    expect(screen.getByText("Lineups")).toBeTruthy();
  });
});
