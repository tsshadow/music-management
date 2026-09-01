import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import App from "../../src/App.svelte";
import TopBar from "../../src/lib/TopBar.svelte";
import {
  activeManagementTab,
  activeSettingsTab,
  activeView,
  credentials,
  isMobile,
  mumaSessionActive,
  mumaUser,
  sidebarDrawerOpen,
} from "../../src/lib/store.js";

/** Answers everything the shell asks for while the management view boots. */
function subsonic() {
  return vi.fn(async (url) => {
    if (url.includes("/rest/getGenres")) {
      return { ok: true, json: async () => ({ "subsonic-response": { genres: { genre: [] } } }) };
    }
    if (url.includes("/release-notes.json")) return { ok: true, json: async () => [] };
    return {
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok", serverVersion: "0.0.57" } }),
    };
  });
}

/**
 * Lands the app on one of the two views that own a sidebar. App reads the view
 * back from the URL on mount, so setting the store alone would not survive.
 *
 * @param {string} view - 'management' or 'settings'.
 */
function startOn(view) {
  window.history.replaceState({}, "", `/${view}`);
  activeView.set(view);
}

/**
 * Finds a management group's header button by its exact label -- an `includes`
 * match would pick up 'Genre Curatie' when looking for the 'Curatie' header.
 *
 * @param {HTMLElement} drawer - The open drawer.
 * @param {string} label - The group label as rendered.
 * @returns {HTMLElement} The header button.
 */
function groupHeader(drawer, label) {
  return [...drawer.querySelectorAll("button")].find((b) => b.textContent.trim() === label);
}

/** Renders the shell and waits until it is past the login screen. */
async function renderApp() {
  render(App);
  await waitFor(() => expect(screen.queryByLabelText("Gebruikersnaam")).toBeNull());
}

describe("mobile sidebar drawer", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    mumaSessionActive.set(false);
    mumaUser.set({ id: 1, username: "user", is_admin: true });
    activeView.set("home");
    activeManagementTab.set("overview");
    activeSettingsTab.set("general");
    sidebarDrawerOpen.set(false);
    isMobile.set(true);
    window.history.replaceState({}, "", "/");
    window.localStorage.clear();
    globalThis.fetch = subsonic();
  });

  afterEach(() => {
    sidebarDrawerOpen.set(false);
    vi.restoreAllMocks();
  });

  it("the player screen has no menu button -- the bottom bar navigates there", () => {
    render(TopBar, { greeting: "Goedemiddag" });

    expect(screen.queryByLabelText("Menu openen")).toBeNull();
  });

  it("the management screen offers a menu button", () => {
    activeView.set("management");

    render(TopBar, { greeting: "" });

    expect(screen.getByLabelText("Menu openen")).toBeTruthy();
  });

  it("the settings screen offers a menu button", () => {
    activeView.set("settings");

    render(TopBar, { greeting: "" });

    expect(screen.getByLabelText("Menu openen")).toBeTruthy();
  });

  it("the menu button opens the drawer", async () => {
    activeView.set("management");

    render(TopBar, { greeting: "" });
    await fireEvent.click(screen.getByLabelText("Menu openen"));

    expect(get(sidebarDrawerOpen)).toBe(true);
  });

  it("stays closed until it is asked for", async () => {
    startOn("management");

    await renderApp();

    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("shows the management tabs once opened", async () => {
    startOn("management");
    await renderApp();

    sidebarDrawerOpen.set(true);

    const drawer = await screen.findByRole("dialog");
    // The management pages sit in collapsible groups now, so the drawer shows the
    // group headers until one of them is opened.
    expect(drawer.textContent).toContain("Curatie");
    await fireEvent.click(groupHeader(drawer, "Curatie"));

    expect(drawer.textContent).toContain("Genre Curatie");
  });

  it("shows the settings tabs on the settings screen", async () => {
    startOn("settings");
    await renderApp();

    sidebarDrawerOpen.set(true);

    const drawer = await screen.findByRole("dialog");
    expect(drawer.textContent).toContain("Geavanceerd");
  });

  it("picking a tab switches to it and closes the drawer again", async () => {
    startOn("management");
    await renderApp();
    sidebarDrawerOpen.set(true);
    const drawer = await screen.findByRole("dialog");

    await fireEvent.click(groupHeader(drawer, "Curatie"));
    const tab = [...drawer.querySelectorAll("button")].find((b) =>
      b.textContent.includes("Genre Curatie"),
    );
    await fireEvent.click(tab);

    expect(get(activeManagementTab)).toBe("genre-curation");
    await waitFor(() => expect(get(sidebarDrawerOpen)).toBe(false));
  });

  it("the backdrop closes the drawer", async () => {
    startOn("management");
    await renderApp();
    sidebarDrawerOpen.set(true);
    await screen.findByRole("dialog");

    await fireEvent.click(screen.getByLabelText("Menu sluiten"));

    await waitFor(() => expect(get(sidebarDrawerOpen)).toBe(false));
  });

  // Leaving management from inside the drawer (the player/management switch in
  // its header) would otherwise leave the overlay hanging over the player.
  it("leaving the screen closes the drawer", async () => {
    startOn("management");
    await renderApp();
    sidebarDrawerOpen.set(true);
    await screen.findByRole("dialog");

    activeView.set("home");

    await waitFor(() => expect(get(sidebarDrawerOpen)).toBe(false));
  });
});
