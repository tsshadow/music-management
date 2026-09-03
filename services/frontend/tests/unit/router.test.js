import { describe, it, expect } from "vitest";
import {
  MANAGEMENT_GROUPS,
  MANAGEMENT_TABS,
  SETTINGS_TABS,
  pathToState,
  viewToPath,
} from "../../src/lib/router.js";

/** The state object App keeps in its stores, with only the fields a route uses. */
function state(view, extra = {}) {
  return { view, loggedIn: true, ...extra };
}

describe("viewToPath", () => {
  it("sends a visitor without a session to the login screen", () => {
    expect(viewToPath({ view: "songs", loggedIn: false })).toBe("/login");
  });

  it("maps the home view to the root path", () => {
    expect(viewToPath(state("home"))).toBe("/");
  });

  it.each([
    ["songs", "/songs"],
    ["sets", "/sets"],
    ["albums", "/albums"],
    ["genres", "/genres"],
    ["labels", "/labels"],
    ["podcasts", "/podcasts"],
    ["artists", "/artists"],
    ["playlists", "/playlists"],
    ["memories", "/memories"],
    ["history", "/history"],
    ["starred", "/starred"],
    ["festivals", "/festivals"],
    ["years", "/years"],
    ["lineups", "/lineups"],
  ])("maps the %s sidebar page to %s", (view, path) => {
    expect(viewToPath(state(view))).toBe(path);
  });

  it("percent-encodes a genre name so a slash in it cannot change the route", () => {
    expect(viewToPath(state("genre:Drum & Bass / UK"))).toBe("/genre/Drum%20%26%20Bass%20%2F%20UK");
  });

  it("percent-encodes a label name the same way", () => {
    expect(viewToPath(state("label:Drum & Bass / UK"))).toBe("/label/Drum%20%26%20Bass%20%2F%20UK");
  });

  it("percent-encodes a show name, which can hold a slash and a hash", () => {
    expect(viewToPath(state("podcast:Q-dance Radio / #40"))).toBe(
      "/podcast/Q-dance%20Radio%20%2F%20%2340",
    );
  });

  it("percent-encodes a festival name, which routinely contains spaces and ampersands", () => {
    expect(viewToPath(state("festival:Q-BASE 2024 & Friends"))).toBe(
      "/festival/Q-BASE%202024%20%26%20Friends",
    );
  });

  it("routes a year like any other argument view", () => {
    expect(viewToPath(state("year:2024"))).toBe("/year/2024");
  });

  it("percent-encodes a lineup name so a slash in it cannot change the route", () => {
    expect(viewToPath(state("lineup:Defqon.1 2025 / Blue"))).toBe(
      "/lineup/Defqon.1%202025%20%2F%20Blue",
    );
  });

  it("puts the memory year in the path", () => {
    expect(viewToPath(state("memories:2025"))).toBe("/memories/2025");
  });

  it("keeps the memories overview on its own path", () => {
    expect(viewToPath(state("memories"))).toBe("/memories");
  });

  it("gives a lineup browse level its own path", () => {
    expect(viewToPath(state("lineups:Defqon.1/2014"))).toBe("/lineups/Defqon.1%2F2014");
  });

  it("keeps the lineup overview on its own path", () => {
    expect(viewToPath(state("lineups"))).toBe("/lineups");
  });

  it("keeps browsing a lineup apart from playing it", () => {
    expect(viewToPath(state("lineup:Defqon.1/2014"))).toBe("/lineup/Defqon.1%2F2014");
  });

  it("puts the artist id in the path", () => {
    expect(viewToPath(state("artist:ar-123"))).toBe("/artist/ar-123");
  });

  it("puts the album id in the path", () => {
    expect(viewToPath(state("album:al-456"))).toBe("/album/al-456");
  });

  it("puts the id of the open playlist in the path", () => {
    expect(viewToPath(state("playlist-detail", { playlistId: "pl-7" }))).toBe("/playlist/pl-7");
  });

  it("leaves the URL alone while an opening playlist has no id yet", () => {
    expect(viewToPath(state("playlist-detail"))).toBeNull();
  });

  it("percent-encodes a search query", () => {
    expect(viewToPath(state("search:drum & bass"))).toBe("/search/drum%20%26%20bass");
  });

  it("names the open settings tab in the path", () => {
    expect(viewToPath(state("settings", { settingsTab: "advanced" }))).toBe("/settings/advanced");
  });

  it("names the open management tab in the path", () => {
    expect(viewToPath(state("management", { managementTab: "scanner" }))).toBe(
      "/management/scanner",
    );
  });

  it("leaves an unknown settings tab out of the path", () => {
    expect(viewToPath(state("settings", { settingsTab: "scan-settings" }))).toBe("/settings");
  });

  it("leaves an unknown management tab out of the path", () => {
    expect(viewToPath(state("management", { managementTab: "nope" }))).toBe("/management");
  });

  it("leaves the URL alone for a view that has no route", () => {
    expect(viewToPath(state("some-future-view"))).toBeNull();
  });
});

describe("pathToState", () => {
  it("reads the root path as the home view", () => {
    expect(pathToState("/")).toEqual({ view: "home" });
  });

  it("reads an empty path as the home view", () => {
    expect(pathToState("")).toEqual({ view: "home" });
  });

  it("reads the login path", () => {
    expect(pathToState("/login")).toEqual({ view: "login" });
  });

  it("falls back to home for a path that matches no route", () => {
    expect(pathToState("/nope/nope")).toEqual({ view: "home" });
  });

  it("decodes a genre name back out of the path", () => {
    expect(pathToState("/genre/Drum%20%26%20Bass%20%2F%20UK")).toEqual({
      view: "genre:Drum & Bass / UK",
    });
  });

  it("decodes a search query back out of the path", () => {
    expect(pathToState("/search/drum%20%26%20bass")).toEqual({ view: "search:drum & bass" });
  });

  it.each([
    ["/festivals", "festivals"],
    ["/years", "years"],
    ["/lineups", "lineups"],
  ])("reads %s back as the %s page", (path, view) => {
    expect(pathToState(path)).toEqual({ view });
  });

  it("decodes a festival name back to exactly what was encoded", () => {
    expect(pathToState("/festival/Q-BASE%202024%20%26%20Friends")).toEqual({
      view: "festival:Q-BASE 2024 & Friends",
    });
  });

  it("decodes a lineup name containing a slash", () => {
    expect(pathToState("/lineup/Defqon.1%202025%20%2F%20Blue")).toEqual({
      view: "lineup:Defqon.1 2025 / Blue",
    });
  });

  it("reads a year path back as a year view", () => {
    expect(pathToState("/year/2024")).toEqual({ view: "year:2024" });
  });

  it("reads a memory year off the path", () => {
    expect(pathToState("/memories/2025")).toEqual({ view: "memories:2025" });
  });

  it("still reads the bare memories path as the overview", () => {
    expect(pathToState("/memories")).toEqual({ view: "memories" });
  });

  it("reads a lineup browse level back", () => {
    expect(pathToState("/lineups/Defqon.1%2F2014")).toEqual({ view: "lineups:Defqon.1/2014" });
  });

  it("still reads the bare lineups path as the overview", () => {
    expect(pathToState("/lineups")).toEqual({ view: "lineups" });
  });

  it("does not confuse browsing a lineup with playing one", () => {
    expect(pathToState("/lineup/Defqon.1%2F2014")).toEqual({ view: "lineup:Defqon.1/2014" });
  });

  it("reads the playlist id off the path", () => {
    expect(pathToState("/playlist/pl-7")).toEqual({ view: "playlist-detail", playlistId: "pl-7" });
  });

  it("reads the settings tab off the path", () => {
    expect(pathToState("/settings/advanced")).toEqual({
      view: "settings",
      settingsTab: "advanced",
    });
  });

  it("reads the management tab off the path", () => {
    expect(pathToState("/management/scanner")).toEqual({
      view: "management",
      managementTab: "scanner",
    });
  });

  it("leaves the stored tab in place when the settings path names no tab", () => {
    expect(pathToState("/settings")).toEqual({ view: "settings" });
  });

  it("leaves the stored tab in place when the management path names no tab", () => {
    expect(pathToState("/management")).toEqual({ view: "management" });
  });

  it("ignores a settings tab that no longer exists rather than showing an empty screen", () => {
    expect(pathToState("/settings/scan-settings")).toEqual({ view: "settings" });
  });

  it("ignores a management tab that no longer exists", () => {
    expect(pathToState("/management/nope")).toEqual({ view: "management" });
  });

  it("ignores a trailing slash", () => {
    expect(pathToState("/songs/")).toEqual({ view: "songs" });
  });
});

describe("round trip", () => {
  const paths = [
    "/",
    "/login",
    "/songs",
    "/sets",
    "/albums",
    "/genres",
    "/labels",
    "/podcasts",
    "/artists",
    "/playlists",
    "/memories",
    "/memories/2025",
    "/history",
    "/starred",
    "/genre/Drum%20%26%20Bass%20%2F%20UK",
    "/label/Hardcore",
    "/podcast/Hard%20With%20Style",
    "/artist/ar-1",
    "/album/al-2",
    "/playlist/pl-3",
    "/search/drum%20%26%20bass",
    ...SETTINGS_TABS.map((tab) => `/settings/${tab}`),
    ...MANAGEMENT_TABS.map((tab) => `/management/${tab}`),
  ];

  it.each(paths)("%s survives being parsed and rebuilt", (path) => {
    const parsed = pathToState(path);
    expect(viewToPath({ ...parsed, loggedIn: path !== "/login" })).toBe(path);
  });
});

describe("edit page routes", () => {
  it("links an artist edit page off the artist it edits", () => {
    expect(viewToPath({ view: "artist-edit:123" })).toBe("/artist/123/edit");
  });

  it("reads an artist edit path back", () => {
    expect(pathToState("/artist/123/edit")).toEqual({ view: "artist-edit:123" });
  });

  it("percent-encodes a genre name in an edit link", () => {
    expect(viewToPath({ view: "genre-edit:Hardcore/Uptempo" })).toBe(
      "/genre/Hardcore%2FUptempo/edit",
    );
  });

  it("does not mistake an edit path for a genre whose name ends in edit", () => {
    expect(pathToState("/genre/Hardcore/edit")).toEqual({ view: "genre-edit:Hardcore" });
  });

  it("still reads a plain genre path as the genre view", () => {
    expect(pathToState("/genre/Hardcore")).toEqual({ view: "genre:Hardcore" });
  });

  it("round-trips a label edit path with spaces in the name", () => {
    const path = viewToPath({ view: "label-edit:Masters of Hardcore" });
    expect(path).toBe("/label/Masters%20of%20Hardcore/edit");
    expect(pathToState(path)).toEqual({ view: "label-edit:Masters of Hardcore" });
  });
});

describe("the configuration tab", () => {
  it("has a route, so a bookmark reopens it", () => {
    expect(viewToPath({ view: "management", managementTab: "config" })).toBe("/management/config");
  });

  it("reads back as the management view on that tab", () => {
    expect(pathToState("/management/config")).toEqual({
      view: "management",
      managementTab: "config",
    });
  });
});

describe("MANAGEMENT_GROUPS", () => {
  const grouped = () => MANAGEMENT_GROUPS.flatMap((group) => group.pages);

  // This is the test that stops the two lists drifting. A tab added to
  // MANAGEMENT_TABS but not to a group would be reachable by URL and invisible in
  // the sidebar; a tab in a group but not in MANAGEMENT_TABS would render a
  // sidebar entry whose route falls back to home.
  it("covers every routable management tab exactly once", () => {
    expect(grouped().slice().sort()).toEqual(MANAGEMENT_TABS.slice().sort());
  });

  it("contains no page that is not routable", () => {
    for (const page of grouped()) {
      expect(MANAGEMENT_TABS).toContain(page);
    }
  });

  it("gives every group a non-empty page list", () => {
    for (const group of MANAGEMENT_GROUPS) {
      expect(group.pages.length).toBeGreaterThan(0);
    }
  });

  // A standalone entry renders as one row rather than a collapsible header, so it
  // has no label of its own -- the page's own label is the row.
  it("only lets a single-page group go without a label", () => {
    for (const group of MANAGEMENT_GROUPS) {
      if (group.labelKey === null) expect(group.pages.length).toBe(1);
      else expect(typeof group.labelKey).toBe("string");
    }
  });

  it("has unique group ids", () => {
    const ids = MANAGEMENT_GROUPS.map((group) => group.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("no longer routes the deleted tabs", () => {
    expect(MANAGEMENT_TABS).not.toContain("versions");
    expect(MANAGEMENT_TABS).not.toContain("about");
  });

  it("sends a stale link to a deleted tab to the management view with no tab", () => {
    expect(pathToState("/management/versions")).toEqual({ view: "management" });
    expect(pathToState("/management/about")).toEqual({ view: "management" });
  });
});
