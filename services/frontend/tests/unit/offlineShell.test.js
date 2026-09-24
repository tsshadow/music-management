import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import OfflineNotice from "../../src/lib/OfflineNotice.svelte";
import Sidebar from "../../src/lib/Sidebar.svelte";
import MobileNav from "../../src/lib/MobileNav.svelte";
import BrowseGrid from "../../src/lib/BrowseGrid.svelte";
import { pathToState, viewToPath } from "../../src/lib/router.js";
import platformModule from "../../src/lib/platform/index.js";
import { credentials, favoriteGenres, viewMode } from "../../src/lib/store.js";
import { offline } from "../../src/lib/subsonic.js";

describe("the downloads route", () => {
  // Reachable everywhere, listed only where it works: a route that existed only
  // inside the shell would make a shared link land on the home screen.
  it("maps both ways like every other plain view", () => {
    expect(viewToPath({ view: "downloads" })).toBe("/downloads");
    expect(pathToState("/downloads")).toEqual({ view: "downloads" });
    expect(pathToState("/downloads/")).toEqual({ view: "downloads" });
  });
});

describe("OfflineNotice", () => {
  it("says a screen needs the server, which is not the same as saying it is empty", () => {
    render(OfflineNotice, { kind: "unavailable" });

    expect(screen.getByText("Niet beschikbaar zonder verbinding")).toBeTruthy();
    expect(screen.getByText(/heeft de server nodig/i)).toBeTruthy();
  });

  it("says a list has nothing downloaded, and offers the way to change that", () => {
    render(OfflineNotice, { kind: "empty", onnavigate: vi.fn() });

    expect(screen.getByText("Hier is niets gedownload")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Downloads" })).toBeTruthy();
  });

  it("is a message, never a spinner", () => {
    render(OfflineNotice, { kind: "unavailable" });

    expect(document.querySelector(".animate-spin")).toBeNull();
  });
});

describe("the Downloads entry in the navigation", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    viewMode.set("songs");
    favoriteGenres.set([]);
    localStorage.clear();
    offline.set(false);
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": {
          status: "ok",
          genres: { genre: [{ value: "Hardcore", songCount: 1200 }] },
        },
      }),
    }));
  });

  afterEach(() => vi.restoreAllMocks());

  // Acceptance criterion 13. Both components read `platform.storage.supported`
  // off the shared object, so this is what a browser tab actually renders.
  it("is absent from the sidebar's library group in a browser", async () => {
    expect(platformModule.storage.supported).toBe(false);

    render(Sidebar, { activeView: "home", onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Hardcore")).toBeTruthy());
    await fireEvent.click(screen.getByText("Bibliotheek"));

    expect(screen.getByText("Albums")).toBeTruthy();
    expect(screen.queryByText("Downloads")).toBeNull();
  });

  it("the phone's bottom bar has no tab of its own for it either", () => {
    render(MobileNav, { activeView: "home", onnavigate: vi.fn() });

    expect(screen.getByText("Favorieten")).toBeTruthy();
    expect(screen.queryByText("Downloads")).toBeNull();
  });

  it("is absent from the phone's browse grid in a browser", () => {
    render(BrowseGrid, { activeView: "playlists", onnavigate: vi.fn() });

    expect(screen.getByText("Albums")).toBeTruthy();
    expect(screen.queryByText("Downloads")).toBeNull();
  });
});
