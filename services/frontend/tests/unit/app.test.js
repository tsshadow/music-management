import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/svelte";
import { get } from "svelte/store";
import App from "../../src/App.svelte";
import {
  activeManagementTab,
  activeModal,
  activeSettingsTab,
  activeView,
  compactPlayerProps,
  credentials,
  currentPlaylist,
  isMobile,
  mumaSessionActive,
  mumaUser,
  playlist,
  searchResultsOpen,
  setupStepsSeen,
  viewMode,
  subsonicToken,
} from "../../src/lib/store.js";
import { recentPlaces, clearRecentPlaces } from "../../src/lib/recentPlaces.js";
import { SETUP_STEPS } from "../../src/lib/setup.js";
import { setLocaleFromAccount } from "../../src/lib/i18n/index.js";
import { platform } from "../../src/lib/platform/index.js";

/** Answers everything the shell and the home screen ask for. */
function subsonic() {
  return vi.fn(async (url) => {
    if (url.includes("/rest/getGenres")) {
      return {
        ok: true,
        json: async () => ({
          "subsonic-response": {
            status: "ok",
            genres: { genre: [{ value: "Hardcore", songCount: 1200 }] },
          },
        }),
      };
    }
    if (url.includes("/rest/getSpotifyPlaylist")) {
      return {
        ok: true,
        json: async () => ({ "subsonic-response": { status: "ok", playlist: { entry: [] } } }),
      };
    }
    if (url.includes("/rest/getSpotifyTracks")) {
      return {
        ok: true,
        json: async () => ({
          "subsonic-response": { status: "ok", tracks: { track: [], moreResults: false } },
        }),
      };
    }
    if (url.includes("/rest/getRecordLabels")) {
      return {
        ok: true,
        json: async () => ({
          "subsonic-response": {
            status: "ok",
            recordLabels: { recordLabel: [{ value: "Art of Creation" }] },
          },
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
 * By its landmark, because the desktop sidebar renders its own "Nummers" and
 * "Sets" too, on the mode switch, and clicking that one proves nothing about
 * the tab strip.
 *
 * @param {string} label - The tab's visible label.
 * @returns {HTMLElement}
 */
function bottomBarTab(label) {
  return within(screen.getByRole("navigation", { name: "Navigatiebalk" })).getByRole("button", {
    name: label,
  });
}

/**
 * One segment of the phone's Songs/Sets mode control (`ModeChips.svelte`),
 * shown in the phone's top bar next to search and the profile button.
 * Unlike the old bottom-bar tabs it replaced, a segment only ever sets
 * `viewMode` -- it never navigates.
 *
 * @param {string} label - The segment's visible label.
 * @returns {HTMLElement}
 */
function modeChip(label) {
  return within(screen.getByRole("group", { name: "Modus wisselen" })).getByRole("button", {
    name: label,
  });
}

describe("App", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "demo-user", password: "pw" });
    subsonicToken.set({ username: "demo-user", token: "test-subsonic-token" });
    mumaSessionActive.set(false);
    activeView.set("home");
    activeModal.set(null);
    viewMode.set("songs");
    playlist.set([]);
    isMobile.set(false);
    // App's own onMount re-derives `isMobile` from the real viewport width, which
    // would otherwise stomp over a test-set store value the instant App mounts.
    Object.defineProperty(window, "innerWidth", { value: 1024, configurable: true });
    currentPlaylist.set(null);
    searchResultsOpen.set(false);
    activeSettingsTab.set("general");
    activeManagementTab.set("overview");
    // Every step seen: the setup tour would otherwise open over every test here. Its own
    // tests below clear this.
    setupStepsSeen.set(SETUP_STEPS.map((step) => step.id));
    // Not mumaUser.set(null): store.js reads that as a logout and resets the
    // language to the browser's, which in jsdom is English -- every assertion
    // on a Dutch label in this file would then fail.
    setLocaleFromAccount("nl");
    // App keeps the view in the URL, so a previous test that ended on /login
    // would otherwise put this one back on the login screen.
    window.history.replaceState({}, "", "/");
    globalThis.fetch = subsonic();
    clearRecentPlaces();
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

  it("opens the setup tour once on a first run and records it when done", async () => {
    setupStepsSeen.set([]);

    render(App);

    await waitFor(() => expect(screen.getByTestId("setup-wizard")).toBeTruthy());
    expect(get(activeView)).toBe("setup");
    expect(screen.getByText("Welkom bij MuMa")).toBeTruthy();

    await fireEvent.click(screen.getByRole("button", { name: "Overslaan" }));

    await waitFor(() => expect(screen.queryByTestId("setup-wizard")).toBeNull());
    expect(get(activeView)).toBe("home");
    expect(get(setupStepsSeen)).toEqual(SETUP_STEPS.filter((s) => !s.native).map((s) => s.id));
  });

  it("opens only the new steps after an update, badged as new", async () => {
    setupStepsSeen.set(SETUP_STEPS.map((s) => s.id).filter((id) => id !== "display"));

    render(App);

    await waitFor(() => expect(screen.getByTestId("setup-step-display")).toBeTruthy());
    expect(screen.getByText("Nieuw sinds je laatste bezoek")).toBeTruthy();
    expect(screen.getByText("Stap 1 van 1")).toBeTruthy();
  });

  it("leaves a listener who has seen every step alone", async () => {
    render(App);

    await waitFor(() => expect(screen.queryByLabelText("Gebruikersnaam")).toBeNull());
    expect(screen.queryByTestId("setup-wizard")).toBeNull();
    expect(get(activeView)).toBe("home");
  });

  it("walks every step again when the manual asks for the tour", async () => {
    render(App);
    await waitFor(() => expect(screen.queryByLabelText("Gebruikersnaam")).toBeNull());

    activeView.set("setup");

    await waitFor(() => expect(screen.getByTestId("setup-wizard")).toBeTruthy());
    expect(
      screen.getByText(`Stap 1 van ${SETUP_STEPS.filter((s) => !s.native).length}`),
    ).toBeTruthy();
    expect(screen.queryByText("Nieuw")).toBeNull();
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

  // Unlike the old bottom-bar tab it replaced, the mode chip is a switch, not a
  // destination: it changes the brand colour everywhere without moving the
  // listener off the tab they were already standing on. The control itself now
  // lives in the phone's top bar, so these render on a phone-sized viewport --
  // setting the `isMobile` store alone would not survive, since App's own
  // onMount re-derives it from `window.innerWidth` as soon as it mounts.
  it("the Sets chip changes the mode without leaving the tab", async () => {
    Object.defineProperty(window, "innerWidth", { value: 375, configurable: true });
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));

    await fireEvent.click(modeChip("Sets"));

    await waitFor(() => expect(get(viewMode)).toBe("sets"));
    expect(get(activeView)).toBe("home");
    // The brand colour the whole app reads off the document.
    expect(document.documentElement.classList.contains("mode-sets")).toBe(true);
  });

  it("the Nummers chip takes the app back out of set mode", async () => {
    Object.defineProperty(window, "innerWidth", { value: 375, configurable: true });
    viewMode.set("sets");
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));

    await fireEvent.click(modeChip("Nummers"));

    await waitFor(() => expect(get(viewMode)).toBe("songs"));
    expect(document.documentElement.classList.contains("mode-sets")).toBe(false);
  });

  // The row above the content that used to hold the mode chips is gone -- the
  // phone's top bar owns the switch now, and a desktop render has no chips at
  // all (the sidebar has its own toggle).
  it("no longer shows a chips row above the content on desktop", async () => {
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));

    expect(screen.queryByRole("group", { name: "Modus wisselen" })).toBeNull();
  });

  // E: handleNavigate is the one spot every navigation passes through, and the one place
  // that records a recent place -- but only for the kinds recentPlaces.js actually tracks.
  it("records a recent place for a genre but not for a plain screen like playlists", async () => {
    render(App);
    await waitFor(() => expect(screen.getByText("Hardcore")).toBeTruthy());

    await fireEvent.click(screen.getByText("Hardcore"));
    await waitFor(() => expect(get(activeView)).toBe("genre:Hardcore"));
    expect(get(recentPlaces).map((p) => p.view)).toEqual(["genre:Hardcore"]);

    await fireEvent.click(bottomBarTab("Bladeren"));
    await fireEvent.click(
      within(screen.getByLabelText("Alles doorbladeren")).getByRole("button", {
        name: "Afspeellijsten",
      }),
    );
    await waitFor(() => expect(get(activeView)).toBe("playlists"));
    expect(get(recentPlaces).map((p) => p.view)).toEqual(["genre:Hardcore"]);
  });

  it("the bottom bar's three tabs move between home, browse and favorites", async () => {
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));

    await fireEvent.click(bottomBarTab("Bladeren"));
    await waitFor(() => expect(get(activeView)).toBe("browse"));
    expect(window.location.pathname).toBe("/browse");
    expect(screen.getByText("Alles doorbladeren")).toBeTruthy();

    await fireEvent.click(bottomBarTab("Favorieten"));
    await waitFor(() => expect(get(activeView)).toBe("favorites"));
    expect(window.location.pathname).toBe("/favorites");
    expect(screen.getByTestId("favorites-view")).toBeTruthy();

    await fireEvent.click(bottomBarTab("Bladeren"));
    await fireEvent.click(
      within(screen.getByLabelText("Alles doorbladeren")).getByRole("button", {
        name: "Afspeellijsten",
      }),
    );
    await waitFor(() => expect(get(activeView)).toBe("playlists"));
    expect(window.location.pathname).toBe("/playlists");
    expect(bottomBarTab("Bladeren")).toHaveClass("text-white");
  });

  // The mirror exists so the shell's Android back handler can close a search
  // result before it falls through to leaving the tab (see App's
  // `handleShellBack`); it must not stay stuck on true once the listener has
  // already left some other way, or a later back press on another tab would
  // wrongly read as "there is a result open here to close".
  it("clears the mirrored search-results flag on leaving the Search tab", async () => {
    render(App);
    await waitFor(() => expect(screen.getAllByText("Afspeellijsten").length).toBeGreaterThan(0));
    activeView.set("search");
    searchResultsOpen.set(true);

    activeView.set("home");

    await waitFor(() => expect(get(searchResultsOpen)).toBe(false));
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
    mumaUser.set({ id: 1, username: "demo-user", is_admin: true });
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

  // `platform.system.carConnected`, wired to the car screen through the ported
  // `car/CarModeSession.kt` (`lib/carMode.js`). `carConnected` and `carState` are spied on
  // rather than driven through a fake bridge, the same shortcut `settingsNavigation.test.js`
  // takes for `isNative` -- this is a browser `platform.system` in every test in this file,
  // and the point here is only what App does with the events, not the bridge plumbing itself.
  describe("car mode auto-open", () => {
    afterEach(() => {
      platform.system.isNative = false;
    });

    it("navigates to the car screen when the shell reports a connection", async () => {
      platform.system.isNative = true;
      let handler;
      vi.spyOn(platform.system, "carConnected").mockImplementation((fn) => {
        handler = fn;
        return () => {};
      });
      vi.spyOn(platform.system, "carState").mockResolvedValue({ connected: false });

      render(App);
      await waitFor(() => expect(handler).toBeTruthy());

      handler(true);

      await waitFor(() => expect(screen.getByTestId("car-mode")).toBeTruthy());
    });

    it("does not reopen the screen after the driver closes it, until the next connection", async () => {
      platform.system.isNative = true;
      let handler;
      vi.spyOn(platform.system, "carConnected").mockImplementation((fn) => {
        handler = fn;
        return () => {};
      });
      vi.spyOn(platform.system, "carState").mockResolvedValue({ connected: false });

      render(App);
      await waitFor(() => expect(handler).toBeTruthy());
      handler(true);
      await waitFor(() => expect(screen.getByTestId("car-mode")).toBeTruthy());

      await fireEvent.click(screen.getByLabelText("Sluiten"));
      await waitFor(() => expect(screen.queryByTestId("car-mode")).toBeNull());

      // A duplicate report of the same connection -- `refreshManual()` re-publishing on
      // the native side, say -- must not reopen a screen the driver just closed.
      handler(true);
      expect(screen.queryByTestId("car-mode")).toBeNull();

      // A real disconnect and reconnect is the next trip, and offers it again.
      handler(false);
      handler(true);
      await waitFor(() => expect(screen.getByTestId("car-mode")).toBeTruthy());
    });

    it("opens on a cold start already in the car", async () => {
      platform.system.isNative = true;
      vi.spyOn(platform.system, "carConnected").mockImplementation(() => () => {});
      vi.spyOn(platform.system, "carState").mockResolvedValue({ connected: true });

      render(App);

      await waitFor(() => expect(screen.getByTestId("car-mode")).toBeTruthy());
    });
  });

  // `docs/designs/miniplayer/`, issue #179. The shell's window mode is spied on, like the car
  // events above; the viewport height is jsdom's `innerHeight`.
  describe("split screen", () => {
    let modeHandler;

    beforeEach(() => {
      modeHandler = null;
      Object.defineProperty(window, "innerHeight", { value: 400, configurable: true });
      vi.spyOn(platform.system, "onWindowModeChanged").mockImplementation((fn) => {
        modeHandler = fn;
        return () => {};
      });
      vi.spyOn(platform.system, "windowMode").mockResolvedValue({ mode: "split" });
    });

    afterEach(() => {
      Object.defineProperty(window, "innerHeight", { value: 768, configurable: true });
    });

    it("shows the compact player in a short split half, without stars", async () => {
      render(App);

      const half = await screen.findByTestId("split-player");
      expect(within(half).getByTestId("compact-player").dataset.variant).toBe("split");
      expect(within(half).queryByTestId("compact-stars")).toBeNull();
    });

    it("gives the half back to the normal screens on Volledige app, until the mode changes", async () => {
      render(App);
      await screen.findByTestId("split-player");

      await fireEvent.click(screen.getByText("Volledige app"));
      await waitFor(() => expect(screen.queryByTestId("split-player")).toBeNull());

      modeHandler("full");
      modeHandler("split");
      await screen.findByTestId("split-player");
    });

    it("offers Maps only where it can open, and opens it next to the app", async () => {
      vi.spyOn(platform.system, "canNavigate").mockResolvedValue({ value: true });
      const navigate = vi.spyOn(platform.system, "navigateAdjacent").mockResolvedValue();
      render(App);

      await fireEvent.click(await screen.findByText("Navigeren naast MuMa"));

      expect(navigate).toHaveBeenCalledTimes(1);
    });

    it("keeps the screen on while it shows and music plays, and lets go after", async () => {
      const keep = vi.spyOn(platform.system, "setKeepScreenOn").mockResolvedValue();
      render(App);
      await screen.findByTestId("split-player");

      compactPlayerProps.set({ ...get(compactPlayerProps), playing: true });
      await waitFor(() => expect(keep).toHaveBeenLastCalledWith({ keepOn: true }));

      await fireEvent.click(screen.getByText("Volledige app"));
      await waitFor(() => expect(keep).toHaveBeenLastCalledWith({ keepOn: false }));
    });

    it("has no Maps button in a browser", async () => {
      render(App);
      await screen.findByTestId("split-player");

      expect(screen.queryByTestId("compact-navigate")).toBeNull();
    });

    it("keeps the normal screens in a tall split half", async () => {
      Object.defineProperty(window, "innerHeight", { value: 700, configurable: true });
      render(App);
      await waitFor(() => expect(platform.system.windowMode).toHaveBeenCalled());
      await Promise.resolve();

      expect(screen.queryByTestId("split-player")).toBeNull();
    });

    it("lets car mode win over the compact player", async () => {
      platform.system.isNative = true;
      vi.spyOn(platform.system, "carConnected").mockImplementation(() => () => {});
      vi.spyOn(platform.system, "carState").mockResolvedValue({ connected: true });
      try {
        render(App);
        await screen.findByTestId("car-mode");

        expect(screen.queryByTestId("split-player")).toBeNull();
      } finally {
        platform.system.isNative = false;
      }
    });

    it("shows only the cover and title in the floating window, and the normal screens after it", async () => {
      render(App);
      await screen.findByTestId("split-player");

      modeHandler("pip");
      const floating = await screen.findByTestId("pip-player");
      expect(within(floating).getByTestId("compact-player").dataset.variant).toBe("pip");
      expect(within(floating).queryByTestId("compact-transport")).toBeNull();
      expect(screen.queryByTestId("split-player")).toBeNull();

      Object.defineProperty(window, "innerHeight", { value: 700, configurable: true });
      modeHandler("full");
      await waitFor(() => expect(screen.queryByTestId("pip-player")).toBeNull());
    });
  });
});
