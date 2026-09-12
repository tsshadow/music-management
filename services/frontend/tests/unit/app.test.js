import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/svelte";
import { get } from "svelte/store";
import App from "../../src/App.svelte";
import {
  activeManagementTab,
  activeModal,
  activeSettingsTab,
  activeView,
  credentials,
  currentPlaylist,
  isMobile,
  mumaSessionActive,
  mumaUser,
  playlist,
  viewMode,
} from "../../src/lib/store.js";
import { setLocaleFromAccount } from "../../src/lib/i18n/index.js";

/** Answers everything the shell and the home screen ask for. */
function subsonic() {
  return vi.fn(async (url) => {
    if (url.includes("/rest/getGenres")) {
      return {
        ok: true,
        json: async () => ({
          "subsonic-response": { genres: { genre: [{ value: "Hardcore", songCount: 1200 }] } },
        }),
      };
    }
    if (url.includes("/rest/getSpotifyPlaylist")) {
      return { ok: true, json: async () => ({ "subsonic-response": { playlist: { entry: [] } } }) };
    }
    if (url.includes("/rest/getSpotifyTracks")) {
      return {
        ok: true,
        json: async () => ({ "subsonic-response": { tracks: { track: [], moreResults: false } } }),
      };
    }
    if (url.includes("/rest/getRecordLabels")) {
      return {
        ok: true,
        json: async () => ({
          "subsonic-response": { recordLabels: { recordLabel: [{ value: "Art of Creation" }] } },
        }),
      };
    }
    if (url.includes("/release-notes.json")) return { ok: true, json: async () => [] };
    return {
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok", serverVersion: "0.0.57" } }),
    };
  });
}

/**
 * One tab of the phone's bottom bar.
 *
 * By its landmark, because the desktop sidebar renders the same two words: the
 * mode switch has a "Nummers" and a "Sets" of its own, and clicking that one
 * proves nothing about the tab strip.
 *
 * @param {string} label - The tab's visible label.
 * @returns {HTMLElement}
 */
function bottomBarTab(label) {
  return within(screen.getByRole("navigation", { name: "Navigatiebalk" })).getByRole("button", {
    name: label,
  });
}

describe("App", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    mumaSessionActive.set(false);
    activeView.set("home");
    activeModal.set(null);
    viewMode.set("songs");
    playlist.set([]);
    isMobile.set(false);
    currentPlaylist.set(null);
    activeSettingsTab.set("general");
    activeManagementTab.set("overview");
    // Not mumaUser.set(null): store.js reads that as a logout and resets the
    // language to the browser's, which in jsdom is English -- every assertion
    // on a Dutch label in this file would then fail.
    setLocaleFromAccount("nl");
    // App keeps the view in the URL, so a previous test that ended on /login
    // would otherwise put this one back on the login screen.
    window.history.replaceState({}, "", "/");
    globalThis.fetch = subsonic();
  });

  afterEach(() => {
    document.documentElement.classList.remove("mode-sets");
    vi.restoreAllMocks();
  });

  it("shows the login screen without a session", async () => {
    credentials.set({ url: "", username: "", password: "" });

    render(App);

    await waitFor(() => expect(screen.getByLabelText("Gebruikersnaam")).toBeTruthy());
  });

  it("a management session alone is enough to get in", async () => {
    credentials.set({ url: "", username: "", password: "" });
    mumaSessionActive.set(true);

    render(App);

    await waitFor(() => expect(screen.queryByLabelText("Gebruikersnaam")).toBeNull());
  });

  it("shows the app once there are credentials", async () => {
    render(App);

    await waitFor(() => expect(screen.queryByLabelText("Gebruikersnaam")).toBeNull());
    expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0);
  });

  it("set mode is marked on the document", async () => {
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));

    viewMode.set("sets");

    await waitFor(() =>
      expect(document.documentElement.classList.contains("mode-sets")).toBe(true),
    );
  });

  it("switching to set mode moves the songs view along", async () => {
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));
    // Set after mounting: App restores the view from the URL on arrival.
    activeView.set("songs");

    viewMode.set("sets");

    await waitFor(() => expect(get(activeView)).toBe("sets"));
  });

  // The tab landed and the route stayed on '/songs': the tap set the view to
  // 'sets' while the mode still said 'songs', and the effect that keeps the two
  // in step put the view straight back. Both halves move or neither does.
  it("the Sets tab in the bottom bar switches the mode and the view together", async () => {
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));
    activeView.set("songs");

    await fireEvent.click(bottomBarTab("Sets"));

    await waitFor(() => expect(get(activeView)).toBe("sets"));
    expect(get(viewMode)).toBe("sets");
    expect(window.location.pathname).toBe("/sets");
    // The brand colour the whole app reads off the document.
    expect(document.documentElement.classList.contains("mode-sets")).toBe(true);
  });

  it("the Nummers tab takes the app back out of set mode", async () => {
    viewMode.set("sets");
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));
    activeView.set("sets");

    await fireEvent.click(bottomBarTab("Nummers"));

    await waitFor(() => expect(get(activeView)).toBe("songs"));
    expect(get(viewMode)).toBe("songs");
    expect(window.location.pathname).toBe("/songs");
  });

  it("switching back to song mode moves the sets view along", async () => {
    viewMode.set("sets");
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));
    activeView.set("sets");

    viewMode.set("songs");

    await waitFor(() => expect(get(activeView)).toBe("songs"));
  });

  it("a non-administrator is bounced off the management screen", async () => {
    activeView.set("management");

    render(App);

    await waitFor(() => expect(get(activeView)).toBe("home"));
  });

  it("puts a label with a slash in it in the URL without breaking the route", async () => {
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));

    activeView.set("label:Drum & Bass / UK");

    await waitFor(() =>
      expect(window.location.pathname).toBe("/label/" + encodeURIComponent("Drum & Bass / UK")),
    );
    // And the round trip: the path parses back into the same view.
    window.history.replaceState({}, "", window.location.pathname);
    window.dispatchEvent(new PopStateEvent("popstate"));
    await waitFor(() => expect(get(activeView)).toBe("label:Drum & Bass / UK"));
  });

  // Every earlier routing test moves the store by hand, which is not how the app
  // navigates: the collection grids write to Dashboard's own copy of the view.
  // Clicking a card is what catches the copy failing to reach the store, and with
  // it the URL -- which left the browser's back button one page behind.
  it("clicking through to a label lands in the URL", async () => {
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));

    activeView.set("labels");
    const card = await screen.findByText("Art of Creation");
    await fireEvent.click(card);

    await waitFor(() => expect(window.location.pathname).toBe("/label/Art%20of%20Creation"));
    expect(get(activeView)).toBe("label:Art of Creation");
  });

  it("a sidebar page that used to have no route now lands in the URL", async () => {
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));

    activeView.set("history");

    await waitFor(() => expect(window.location.pathname).toBe("/history"));
  });

  it("the open playlist is named in the URL", async () => {
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));

    currentPlaylist.set({ id: "pl-7", name: "Zaterdag" });
    activeView.set("playlist-detail");

    await waitFor(() => expect(window.location.pathname).toBe("/playlist/pl-7"));
  });

  it("the open settings tab is named in the URL", async () => {
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));

    activeView.set("settings");
    activeSettingsTab.set("advanced");

    await waitFor(() => expect(window.location.pathname).toBe("/settings/advanced"));
  });

  it("a settings tab in the URL is opened on arrival", async () => {
    window.history.replaceState({}, "", "/settings/about");

    render(App);

    await waitFor(() => expect(get(activeSettingsTab)).toBe("about"));
    expect(get(activeView)).toBe("settings");
  });

  it("a management tab in the URL is opened on arrival", async () => {
    mumaUser.set({ id: 1, username: "user", is_admin: true });
    window.history.replaceState({}, "", "/management/scanner");

    render(App);

    await waitFor(() => expect(get(activeManagementTab)).toBe("scanner"));
    expect(get(activeView)).toBe("management");
  });

  it("keeps the stored tab when the settings URL names none", async () => {
    activeSettingsTab.set("advanced");
    window.history.replaceState({}, "", "/settings");

    render(App);

    await waitFor(() => expect(get(activeView)).toBe("settings"));
    expect(get(activeSettingsTab)).toBe("advanced");
  });

  it("the search results modal is shown when it is opened", async () => {
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));

    activeModal.set({ type: "search-results", data: { query: "angerfist", category: "tracks" } });

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/rest/search3"))).toBe(true),
    );
  });
});
