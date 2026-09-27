import { describe, it, expect, vi } from "vitest";
import { createRawSnippet } from "svelte";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/svelte";
import LazyView from "../../src/lib/LazyView.svelte";
import ListEnd from "../../src/lib/ListEnd.svelte";
import {
  adminNextChunks,
  chunksForState,
  createLazyRegistry,
  lazyViews,
  likelyNextChunks,
  managementTabs,
  nextSettingsTab,
  preloadOnIdle,
  preloadState,
  settingsTabName,
  settingsTabs,
  visibleSettingsTabs,
} from "../../src/lib/lazyViews.js";
import { MANAGEMENT_TABS, SETTINGS_TABS } from "../../src/lib/router.js";

/** A promise with its resolve/reject handed out, to hold a chunk "on its way". */
function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Names of what `chunksForState` returns, readable in an assertion. */
const names = (pairs) =>
  pairs.map(
    ([registry, name]) =>
      `${registry === managementTabs ? "tab:" : registry === settingsTabs ? "settings:" : ""}${name}`,
  );

describe("createLazyRegistry", () => {
  it("fetches a chunk once, however often it is asked for", async () => {
    const loader = vi.fn(() => Promise.resolve({ default: "Component" }));
    const registry = createLazyRegistry({ page: loader });

    const [a, b] = await Promise.all([registry.load("page"), registry.load("page")]);
    await registry.load("page");

    expect(a).toBe("Component");
    expect(b).toBe("Component");
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("peeks only once the chunk is in", async () => {
    const held = deferred();
    const registry = createLazyRegistry({ page: () => held.promise });

    const loading = registry.load("page");
    expect(registry.peek("page")).toBeNull();
    held.resolve({ default: "Component" });
    await loading;

    expect(registry.peek("page")).toBe("Component");
  });

  it("forgets a failed fetch, so the retry fetches again", async () => {
    const loader = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ default: "Component" });
    const registry = createLazyRegistry({ page: loader });

    await expect(registry.load("page")).rejects.toThrow("offline");
    await expect(registry.load("page")).resolves.toBe("Component");
    expect(loader).toHaveBeenCalledTimes(2);
  });

  it("treats a chunk Vite gave up on (the reload is coming) as a failure, and retries it", async () => {
    const loader = vi
      .fn()
      .mockResolvedValueOnce(undefined)
      .mockResolvedValueOnce({ default: "Component" });
    const registry = createLazyRegistry({ page: loader });

    await expect(registry.load("page")).rejects.toThrow(/could not be loaded/);
    await expect(registry.load("page")).resolves.toBe("Component");
  });

  it("rejects a name it does not know", async () => {
    const registry = createLazyRegistry({});
    expect(registry.has("nope")).toBe(false);
    await expect(registry.load("nope")).rejects.toThrow(/Unknown lazy view/);
  });
});

describe("the app's lazy views", () => {
  it("has a chunk for every management tab except Scrobble, which binds props", () => {
    const expected = MANAGEMENT_TABS.filter((tab) => tab !== "scrobble").sort();
    expect(managementTabs.names().sort()).toEqual(expected);
  });

  it("has a chunk for every settings tab", () => {
    expect(settingsTabs.names().sort()).toEqual([...SETTINGS_TABS].sort());
  });

  it("resolves the settings tab Settings renders, and the one likely opened next", () => {
    expect(visibleSettingsTabs(false)).toEqual(["general", "advanced", "about", "help"]);
    expect(visibleSettingsTabs(true)).toEqual(["general", "advanced", "about", "help", "device"]);
    expect(settingsTabName("about", false)).toBe("about");
    // `device` outside the shell, and a removed admin tab, show General.
    expect(settingsTabName("device", false)).toBe("general");
    expect(settingsTabName("device", true)).toBe("device");
    expect(settingsTabName("scanner", true)).toBe("general");
    expect(settingsTabName(undefined, false)).toBe("general");
    expect(nextSettingsTab("general", false)).toBe("advanced");
    expect(nextSettingsTab("help", false)).toBe("general");
    expect(nextSettingsTab("help", true)).toBe("device");
    expect(nextSettingsTab("device", true)).toBe("general");
  });

  it("every loader resolves to a component", async () => {
    for (const registry of [lazyViews, managementTabs, settingsTabs]) {
      for (const name of registry.names()) {
        expect(typeof (await registry.load(name)), name).toBe("function");
      }
    }
    // Compiling every lazily loaded view in jsdom takes a while.
  }, 120_000);

  it("maps a view to the chunks it needs on screen", () => {
    expect(names(chunksForState({ view: "home" }))).toEqual([]);
    expect(names(chunksForState({ view: "login" }))).toEqual([]);
    // One tap away (issue #118): the page chunks, and the list pages' parts.
    expect(names(chunksForState({ view: "artist:12" }))).toEqual(["artistPage"]);
    expect(names(chunksForState({ view: "album:9" }))).toEqual(["albumPage"]);
    expect(names(chunksForState({ view: "preset:4" }))).toEqual(["presetPage"]);
    expect(names(chunksForState({ view: "playlist-detail" }))).toEqual(["playlistPage"]);
    expect(names(chunksForState({ view: "release-radar" }))).toEqual(["feedPage"]);
    expect(names(chunksForState({ view: "daily-mix" }))).toEqual(["feedPage"]);
    expect(names(chunksForState({ view: "daily-mix-hard" }))).toEqual(["feedPage"]);
    expect(names(chunksForState({ view: "songs" }))).toEqual(["filterBar"]);
    expect(names(chunksForState({ view: "artists" }))).toEqual(["filterBar"]);
    expect(names(chunksForState({ view: "genre:Hardcore" }))).toEqual(["filterBar"]);
    expect(names(chunksForState({ view: "lineup:x" }))).toEqual(["filterBar"]);
    expect(names(chunksForState({ view: "genres" }))).toEqual(["collectionGrid"]);
    expect(names(chunksForState({ view: "lineups:x" }))).toEqual(["collectionGrid"]);
    expect(names(chunksForState({ view: "playlists" }))).toEqual(["collectionBar"]);
    // Settings fetches its open tab too (issue #119), General when none is named.
    expect(names(chunksForState({ view: "settings" }))).toEqual([
      "settings",
      "settingsSidebar",
      "settings:general",
    ]);
    expect(names(chunksForState({ view: "settings", settingsTab: "about" }))).toEqual([
      "settings",
      "settingsSidebar",
      "settings:about",
    ]);
    expect(names(chunksForState({ view: "management", managementTab: "users" }))).toEqual([
      "management",
      "managementSidebar",
      "tab:users",
    ]);
    // Scrobble lives in the management chunk itself.
    expect(names(chunksForState({ view: "management", managementTab: "scrobble" }))).toEqual([
      "management",
      "managementSidebar",
    ]);
    expect(names(chunksForState({ view: "listening" }))).toEqual(["listening"]);
    expect(names(chunksForState({ view: "memories:2024" }))).toEqual(["memoriesYear"]);
    expect(names(chunksForState({ view: "song:7" }))).toEqual(["song"]);
    expect(names(chunksForState({ view: "new-preset" }))).toEqual(["presetBuilder"]);
    expect(names(chunksForState({ view: "preset-edit:3" }))).toEqual(["presetBuilder"]);
    expect(names(chunksForState({ view: "genre-edit:Hardcore" }))).toEqual(["genreEdit"]);
    expect(names(chunksForState({ view: "voice" }))).toEqual(["voice"]);
  });

  it("preloadState never rejects, even when a chunk fails", async () => {
    const load = vi.spyOn(lazyViews, "load").mockRejectedValue(new Error("gone"));

    await expect(preloadState({ view: "listening" })).resolves.toBeUndefined();

    expect(load).toHaveBeenCalledWith("listening");
    load.mockRestore();
  });

  it("preloads the likely next views one idle slot at a time, admins get Beheer too", async () => {
    const slots = [];
    const requestIdle = (cb) => slots.push(cb);
    const loader = vi.fn(() => Promise.resolve({ default: "C" }));
    const registry = createLazyRegistry({ a: loader, b: loader });

    const done = preloadOnIdle(
      [
        [registry, "a"],
        [registry, "b"],
      ],
      { requestIdle },
    );
    await waitFor(() => expect(slots).toHaveLength(1));
    expect(loader).not.toHaveBeenCalled();
    slots[0]();
    await waitFor(() => expect(slots).toHaveLength(2));
    expect(loader).toHaveBeenCalledTimes(1);
    slots[1]();
    await done;
    expect(loader).toHaveBeenCalledTimes(2);

    expect(names(likelyNextChunks())).toContain("settings");
    expect(names(likelyNextChunks())).toContain("settings:general");
    // The full-screen player first (issue #119), then the artist and album pages: the most
    // common taps should never wait for a file.
    expect(names(likelyNextChunks()).slice(0, 3)).toEqual([
      "nowPlaying",
      "artistPage",
      "albumPage",
    ]);
    expect(names(likelyNextChunks())).not.toContain("management");
    expect(names(adminNextChunks())).toEqual(["management", "managementSidebar", "tab:overview"]);
  });
});

describe("LazyView", () => {
  it("shows skeleton rows while the chunk is on its way, then the view with its props", async () => {
    const held = deferred();
    const registry = createLazyRegistry({ page: () => held.promise });

    render(LazyView, {
      props: { name: "page", registry, props: { hasMore: true, testid: "lazy-pill" } },
    });

    expect(screen.getByTestId("lazy-view-loading")).toBeTruthy();
    expect(screen.getByTestId("skeleton-rows")).toBeTruthy();
    held.resolve({ default: ListEnd });

    expect(await screen.findByTestId("lazy-pill")).toBeTruthy();
    expect(screen.queryByTestId("lazy-view-loading")).toBeNull();
  });

  it("renders at once when the chunk is already in", async () => {
    const registry = createLazyRegistry({ page: () => Promise.resolve({ default: ListEnd }) });
    await registry.load("page");

    render(LazyView, {
      props: { name: "page", registry, props: { hasMore: true, testid: "lazy-pill" } },
    });

    expect(screen.getByTestId("lazy-pill")).toBeTruthy();
    expect(screen.queryByTestId("lazy-view-loading")).toBeNull();
  });

  it("shows the placeholder snippet while loading, then the view (issue #118)", async () => {
    const held = deferred();
    const registry = createLazyRegistry({ page: () => held.promise });
    const placeholder = createRawSnippet(() => ({
      render: () => '<h1 data-testid="seeded-heading">Angerfist</h1>',
    }));

    render(LazyView, {
      props: { name: "page", registry, placeholder, props: { hasMore: true, testid: "lazy-pill" } },
    });

    expect(screen.getByTestId("seeded-heading")).toBeTruthy();
    expect(screen.queryByTestId("lazy-view-loading")).toBeNull();
    held.resolve({ default: ListEnd });

    expect(await screen.findByTestId("lazy-pill")).toBeTruthy();
    expect(screen.queryByTestId("seeded-heading")).toBeNull();
  });

  it("shows nothing while loading when told to, for overlays and sidebars", () => {
    const registry = createLazyRegistry({ page: () => new Promise(() => {}) });

    const { container } = render(LazyView, { props: { name: "page", registry, fallback: "none" } });

    expect(screen.queryByTestId("lazy-view-loading")).toBeNull();
    expect(container.textContent.trim()).toBe("");
  });

  it("says a failed chunk failed, and the retry pill fetches it again", async () => {
    const loader = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce({ default: ListEnd });
    const registry = createLazyRegistry({ page: loader });
    const error = vi.spyOn(console, "error").mockImplementation(() => {});

    render(LazyView, {
      props: { name: "page", registry, props: { hasMore: true, testid: "lazy-pill" } },
    });

    const failure = await screen.findByTestId("section-error");
    await fireEvent.click(within(failure).getByRole("button"));

    expect(await screen.findByTestId("lazy-pill")).toBeTruthy();
    expect(loader).toHaveBeenCalledTimes(2);
    error.mockRestore();
  });

  it("follows a change of props without reloading the view", async () => {
    const loader = vi.fn(() => Promise.resolve({ default: ListEnd }));
    const registry = createLazyRegistry({ page: loader });

    const view = render(LazyView, {
      props: { name: "page", registry, props: { hasMore: true, testid: "lazy-pill" } },
    });
    await screen.findByTestId("lazy-pill");
    await view.rerender({
      props: {
        name: "page",
        registry,
        props: { hasMore: false, ended: true, testid: "lazy-pill" },
      },
    });

    expect(await screen.findByTestId("lazy-pill-end")).toBeTruthy();
    expect(loader).toHaveBeenCalledTimes(1);
  });
});
