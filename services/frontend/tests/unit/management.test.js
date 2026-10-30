import { describe, it, expect, vi, beforeEach, afterEach, beforeAll } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import Management from "../../src/lib/management/Management.svelte";
import {
  activeManagementTab,
  credentials,
  mumaApiKey,
  mumaUser,
  userPermissions,
} from "../../src/lib/store.js";
import { setLocaleFromAccount, t } from "../../src/lib/i18n/index.js";
import { LAZY_HOOK_TIMEOUT_MS, loadLazy } from "./lazyTestUtils.js";
import { managementTabs } from "../../src/lib/lazyViews.js";

// The views below are separate chunks (lazyViews.js). Loaded before any test renders, they are
// on the first frame instead of after a compile that can outlast `waitFor`'s second on a busy
// runner (issue #120).
beforeAll(
  () =>
    loadLazy(
      ...["overview", "health", "events", "user-requests", "genre-curation", "artist-curation"].map(
        (tab) => [managementTabs, tab],
      ),
    ),
  LAZY_HOOK_TIMEOUT_MS,
);

const STATS = {
  total_tracks: 12345,
  total_artists: 678,
  total_scrobbles: 90123,
  match_rate: 92,
  avg_track_duration: 245,
  total_unmatched: 42,
  top_genres: [],
  recently_added: [],
};

const USER = {
  id: 1,
  username: "demo-user",
  display_name: "Demo-User",
  permissions: ["users.read"],
};

/** Answers every endpoint Management loads on arrival. */
function api({
  configOk = true,
  verify = { type: "user", user: USER },
  loginOk = true,
  rejectKey = null,
  failing = [],
} = {}) {
  const bodies = {
    "/api/config": { version: "0.0.57" },
    "/api/notes": { release_notes: "<p>Notes</p>" },
    "/api/rules": { genres: [] },
    "/api/soundcloud": [],
    "/api/youtube": [],
    "/api/all-notes": {},
    "/api/scrobble/import/latest": [],
    "/api/users": [USER],
    "/api/system/containers": [{ name: "music-manager", image: "muma:0.0.57", status: "running" }],
    "/api/system/activity": { recent_added: [], recent_tagged: [] },
    "/api/stats": STATS,
    "/api/roles": [],
    "/api/artist-images/stats": { total: 0, missing: 0 },
    "/api/events": { events: [], counts: {}, total: 0 },
  };

  return vi.fn(async (url, options = {}) => {
    if (url.includes("/api/auth/login")) {
      return { ok: loginOk, json: async () => ({ api_key: "key-from-login" }) };
    }
    if (url.includes("/api/auth/verify")) {
      return { ok: true, json: async () => verify };
    }
    if (url.includes("/api/config") && !configOk) {
      return { ok: false, status: 401, json: async () => ({}) };
    }
    // A key the backend no longer accepts -- e.g. a system key left in
    // localStorage after the deployment stopped resolving one.
    if (rejectKey && options.headers?.["X-API-Key"] === rejectKey) {
      return { ok: false, status: 401, json: async () => ({}) };
    }
    if (failing.some((path) => url.includes(path))) {
      return { ok: false, status: 500, json: async () => ({ detail: "Internal Server Error" }) };
    }
    // Before the generic '/api/rules' entry below, which would otherwise answer
    // the genre table with an object and leave it summarising a non-iterable.
    if (url.includes("/api/rules/genres")) {
      return { ok: true, json: async () => [] };
    }
    const match = Object.keys(bodies).find((path) => url.includes(path));
    return { ok: true, json: async () => (match ? bodies[match] : {}) };
  });
}

describe("Management", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "demo-user" });
    mumaApiKey.set("key-1");
    // The screen is gated on being an administrator; without this it renders the
    // access-denied panel instead of any tab. The verify call overwrites both.
    mumaUser.set({ id: 1, username: "demo-user", is_admin: true });
    userPermissions.set(["users.read"]);
    activeManagementTab.set("overview");
    globalThis.fetch = api();
  });

  afterEach(() => {
    // Unmount before the mocks go: the screen polls for image-fetch progress on
    // an interval, and a poll that outlives the test logs into a torn-down
    // worker, which vitest reports as an unhandled rejection.
    cleanup();
    vi.restoreAllMocks();
  });

  it("opens on the overview once everything is loaded", async () => {
    render(Management);

    await waitFor(() => expect(screen.getByText("1 / 1 Running")).toBeTruthy());
  });

  it("loads its data with the stored api key", async () => {
    render(Management);

    await waitFor(() => expect(screen.getByText("1 / 1 Running")).toBeTruthy());
    const [, options] = globalThis.fetch.mock.calls.find(([url]) => url.includes("/api/config"));
    expect(options.headers["X-API-Key"]).toBe("key-1");
  });

  // Issue #101: no password is stored, so there is nothing to log in with automatically.
  it("without a key the screen stays closed and logs in with nothing", async () => {
    mumaApiKey.set("");

    render(Management);

    await waitFor(() => expect(screen.queryByText("1 / 1 Running")).toBeNull());
    expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/api/auth/login"))).toBe(
      false,
    );
  });

  it("a key the server rejects leaves the management screen closed", async () => {
    globalThis.fetch = api({ configOk: false });

    render(Management);

    await waitFor(() => expect(screen.queryByText("1 / 1 Running")).toBeNull());
  });

  // Issue #101: a refused key used to be traded for a fresh one with the stored password. The key
  // is permanent and no password is stored, so the session ends and the login page comes back.
  it("a stored key the server refuses ends the session instead of logging in again", async () => {
    globalThis.fetch = api({ rejectKey: "key-1" });

    render(Management);

    await waitFor(() => expect(get(mumaApiKey)).toBe(""));
    expect(get(credentials).username).toBe("");
    expect(screen.queryByText("1 / 1 Running")).toBeNull();
    expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/api/auth/login"))).toBe(
      false,
    );
    // Ending the session drops the interface language back to the browser's; later tests read
    // Dutch text.
    setLocaleFromAccount("nl");
  });

  it("the signed-in user and their permissions are published", async () => {
    render(Management);

    await waitFor(() => expect(get(mumaUser)).toEqual(USER));
    expect(get(userPermissions)).toEqual(["users.read"]);
  });

  it("a leftover shared system key ends the session instead of making an administrator", async () => {
    // LMS used to answer every web login with its own api-key, which MuMa
    // verifies as a system key -- and this screen then made the holder an
    // administrator. The login now hands out the user's own key, so a system
    // key in storage is a leftover: it goes, and the user signs in once more.
    globalThis.fetch = api({ verify: { type: "system" } });

    render(Management);

    await waitFor(() => expect(get(mumaApiKey)).toBe(""));
    expect(get(mumaUser)).toBe(null);
    expect(get(userPermissions)).toEqual([]);
    expect(get(credentials).username).toBe("");
    expect(screen.queryByText("1 / 1 Running")).toBeNull();
    expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/api/stats"))).toBe(false);
    // Ending the session is a logout, which drops the interface language back to the
    // browser's (English here); the tests after this one read Dutch text.
    setLocaleFromAccount("nl");
  });

  it("a tab that no longer exists falls back to the overview instead of an empty screen", async () => {
    activeManagementTab.set("scan-settings");

    render(Management);

    await waitFor(() => expect(get(activeManagementTab)).toBe("overview"));
  });

  it("the health tab is reachable", async () => {
    activeManagementTab.set("health");

    render(Management);

    await waitFor(() => expect(screen.getByText("Docker Containers")).toBeTruthy());
  });

  it("the event log tab is reachable", async () => {
    activeManagementTab.set("events");

    render(Management);

    await waitFor(() =>
      expect(screen.getByText(get(t)("management.events.subtitle"))).toBeTruthy(),
    );
  });

  it("the user requests tab is reachable", async () => {
    activeManagementTab.set("user-requests");

    render(Management);

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/api/user-requests"))).toBe(
        true,
      ),
    );
  });

  it("the genre curation tab is reachable", async () => {
    activeManagementTab.set("genre-curation");

    render(Management);

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/api/rules/genres"))).toBe(
        true,
      ),
    );
  });

  it("the artist curation tab is reachable", async () => {
    activeManagementTab.set("artist-curation");

    render(Management);

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/api/rules/artists"))).toBe(
        true,
      ),
    );
  });

  it("survives a server it cannot reach at all", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });

    render(Management);

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
  });

  // /api/versions answered the same music-manager version for every worker and never
  // contacted one, so the tab it fed was showing one number six times. With the tab
  // gone, the request is one fewer round trip on every management page load.
  it("no longer asks for the worker versions", async () => {
    render(Management);

    // Waiting on the first fetch would only catch the auth call that runs before
    // the batch; /api/stats is the last entry of that batch, so its arrival is
    // what says every request the screen makes on load has been made.
    const urls = () => globalThis.fetch.mock.calls.map(([url]) => String(url));
    await waitFor(() => expect(urls().some((url) => url.includes("/api/stats"))).toBe(true));
    expect(urls().some((url) => url.includes("/api/versions"))).toBe(false);
  });

  // fetchMumaJson used to hand an error body back as data, so a failed section was assigned
  // `{detail: ...}` in place of its list. Now a failed call leaves that section at its default.
  it("one section that fails stays empty without taking the rest down or raising the banner", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    globalThis.fetch = api({ failing: ["/api/system/containers"] });

    render(Management);

    await waitFor(() => expect(screen.getByText("0 / 0 Running")).toBeTruthy());
    expect(screen.queryByText("Kon gegevens niet ophalen van de Management API.")).toBeNull();
  });
});
