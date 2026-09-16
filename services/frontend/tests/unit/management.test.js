import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
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
import { t } from "../../src/lib/i18n/index.js";

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

const USER = { id: 1, username: "user", display_name: "Teun", permissions: ["users.read"] };

/** Answers every endpoint Management loads on arrival. */
function api({
  configOk = true,
  verify = { type: "user", user: USER },
  loginOk = true,
  rejectKey = null,
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
    credentials.set({ url: "", username: "user", password: "pw" });
    mumaApiKey.set("key-1");
    // The screen is gated on being an administrator; without this it renders the
    // access-denied panel instead of any tab. The verify call overwrites both.
    mumaUser.set({ id: 1, username: "user", is_admin: true });
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

  it("logs in with the player credentials when there is no key yet", async () => {
    mumaApiKey.set("");

    render(Management);

    await waitFor(() => expect(get(mumaApiKey)).toBe("key-from-login"));
  });

  it("a failed auto-login leaves the management screen closed", async () => {
    mumaApiKey.set("");
    globalThis.fetch = api({ loginOk: false });

    render(Management);

    await waitFor(() => expect(screen.queryByText("1 / 1 Running")).toBeNull());
  });

  it("a key the server rejects leaves the management screen closed", async () => {
    globalThis.fetch = api({ configOk: false });

    render(Management);

    await waitFor(() => expect(screen.queryByText("1 / 1 Running")).toBeNull());
  });

  it("trades a stored key the server rejects for a fresh one instead of staying closed", async () => {
    // Without this the screen wedges permanently: it only ever auto-logs in
    // when there is no key at all, so a stale-but-present key in localStorage
    // meant every visit rendered "kan niet verbinden" until the user cleared
    // their browser storage by hand.
    globalThis.fetch = api({ rejectKey: "key-1" });

    render(Management);

    await waitFor(() => expect(screen.getByText("1 / 1 Running")).toBeTruthy());
    expect(get(mumaApiKey)).toBe("key-from-login");
  });

  it("the signed-in user and their permissions are published", async () => {
    render(Management);

    await waitFor(() => expect(get(mumaUser)).toEqual(USER));
    expect(get(userPermissions)).toEqual(["users.read"]);
  });

  it("the shared system key counts as an administrator", async () => {
    globalThis.fetch = api({ verify: { type: "system" } });

    render(Management);

    await waitFor(() => expect(get(userPermissions)).toEqual([]));
    expect(get(mumaUser)?.is_admin).toBe(true);
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
});
