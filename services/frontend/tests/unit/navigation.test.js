import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/svelte";
import { vi } from "vitest";
import {
  LIBRARY_SECTIONS,
  PERSONAL_SECTIONS,
  browseSections,
  librarySections,
} from "../../src/lib/navigation.js";
import { LIBRARY_TAB_VIEWS, pathToState, viewToPath } from "../../src/lib/router.js";
import { COLLECTION_MODES } from "../../src/lib/collections.js";
import { TILE_COLORS } from "../../src/lib/browseColors.js";
import Sidebar from "../../src/lib/Sidebar.svelte";
import BrowseGrid from "../../src/lib/BrowseGrid.svelte";
import { credentials, viewMode } from "../../src/lib/store.js";

const NATIVE = { storage: { supported: true } };
const BROWSER = { storage: { supported: false } };

describe("navigation sections", () => {
  it("every Browse tile has a colour of its own", () => {
    const ids = [...browseSections("songs", NATIVE), ...browseSections("sets", NATIVE)].map(
      (s) => s.id,
    );
    expect(ids.filter((id) => !TILE_COLORS[id])).toEqual([]);
  });

  it("every section has a route of its own", () => {
    for (const { id } of browseSections("songs", NATIVE)) {
      expect(viewToPath({ view: id })).toBe(`/${id}`);
      expect(pathToState(`/${id}`)).toEqual({ view: id });
    }
  });

  it("every section is owned by the phone's Browse tab", () => {
    const ids = new Set([
      ...browseSections("songs", NATIVE).map((s) => s.id),
      ...browseSections("sets", NATIVE).map((s) => s.id),
    ]);
    expect(new Set(LIBRARY_TAB_VIEWS)).toEqual(ids);
  });

  it("keeps downloads out of a browser", () => {
    expect(librarySections("songs", BROWSER).map((s) => s.id)).not.toContain("downloads");
    expect(librarySections("songs", NATIVE).map((s) => s.id)).toContain("downloads");
    expect(librarySections("songs", undefined).map((s) => s.id)).not.toContain("downloads");
  });

  it("applies the same per-mode gate the collections module declares", () => {
    for (const [id, modes] of Object.entries(COLLECTION_MODES)) {
      for (const mode of ["songs", "sets"]) {
        const shown = librarySections(mode, NATIVE).some((s) => s.id === id);
        expect(shown, `${id} in ${mode}`).toBe(modes.includes(mode));
      }
    }
  });

  it("leads with the list of the mode it is asked for", () => {
    expect(browseSections("songs", NATIVE)[0].id).toBe("songs");
    expect(browseSections("sets", NATIVE)[0].id).toBe("sets");
    expect(browseSections("nonsense", NATIVE)[0].id).toBe("songs");
  });

  it("gives every section a label key and an icon", () => {
    for (const section of [...LIBRARY_SECTIONS, ...PERSONAL_SECTIONS]) {
      expect(section.labelKey).toMatch(/^nav\./);
      expect(section.icon).toMatch(/^M/);
    }
  });
});

/**
 * The reason the module exists: what the desktop sidebar lists and what the phone's grid
 * tiles must be the same set, read off the rendered DOM rather than the constants, so a
 * component that stopped consulting the shared list would fail here.
 */
describe("sidebar and browse grid agree", () => {
  it.each(["songs", "sets"])("in %s mode", async (mode) => {
    credentials.set({ url: "", username: "user", password: "pw" });
    viewMode.set(mode);
    localStorage.setItem("muma_sidebar_library_open", "true");
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ "subsonic-response": { genres: { genre: [] } } }),
    }));

    const sidebar = render(Sidebar, { activeView: "home", onnavigate: vi.fn() });
    const sidebarLabels = Array.from(sidebar.container.querySelectorAll("li button"))
      .map((button) => button.textContent.trim())
      .filter((label) => label && label !== "Home" && label !== "Bibliotheek");
    sidebar.unmount();

    render(BrowseGrid, { onnavigate: vi.fn(), platform: BROWSER });
    const gridLabels = screen.getAllByRole("button").map((button) => button.textContent.trim());

    expect(gridLabels).toEqual(sidebarLabels);
  });
});
