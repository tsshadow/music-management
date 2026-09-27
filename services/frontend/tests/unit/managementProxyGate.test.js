import { describe, it, expect, vi, beforeEach, afterEach, beforeAll } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/svelte";
import Management from "../../src/lib/management/Management.svelte";
import { credentials, mumaApiKey, mumaUser, userPermissions } from "../../src/lib/store.js";
import { LAZY_HOOK_TIMEOUT_MS, loadLazy } from "./lazyTestUtils.js";
import { managementTabs } from "../../src/lib/lazyViews.js";

// The views below are separate chunks (lazyViews.js). Loaded before any test renders, they are
// on the first frame instead of after a compile that can outlast `waitFor`'s second on a busy
// runner (issue #120).
beforeAll(() => loadLazy([managementTabs, "overview"]), LAZY_HOOK_TIMEOUT_MS);

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

const BODIES = {
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
  "/api/artists": [],
  "/api/labels": [],
};

/**
 * The MuMa API as it is really reached: through the LMS proxy, which refuses
 * anything past its concurrency gate.
 *
 * The refusal is not JSON -- MumaResource.cpp writes the bare line
 * "Too many requests to MuMa in flight" with status 503 -- so calling json()
 * on it throws the same SyntaxError the browser reports.
 */
function gatedApi(limit) {
  let inFlight = 0;
  let refusals = 0;

  const fetchMock = vi.fn(async (url) => {
    if (url.includes("/api/auth/verify")) {
      return { ok: true, status: 200, json: async () => ({ type: "user", user: USER }) };
    }
    if (inFlight >= limit) {
      refusals += 1;
      return {
        ok: false,
        status: 503,
        text: async () => "Too many requests to MuMa in flight",
        json: async () => {
          throw new SyntaxError("Unexpected token 'T', \"Too many r\"... is not valid JSON");
        },
      };
    }
    inFlight += 1;
    try {
      await new Promise((resolve) => setTimeout(resolve, 1));
      const path = Object.keys(BODIES).find((candidate) => url.includes(candidate));
      return { ok: true, status: 200, json: async () => (path ? BODIES[path] : {}) };
    } finally {
      inFlight -= 1;
    }
  });

  return { fetchMock, refusalCount: () => refusals };
}

describe("Management behind the LMS proxy gate", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    mumaApiKey.set("key-1");
    mumaUser.set({ id: 1, username: "user", is_admin: true });
    userPermissions.set(["users.read"]);
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("loads every panel without tripping the gate", async () => {
    // The proxy allows half the LMS http thread pool -- four calls on the
    // eight cores production had before the pool was pinned to sixteen.
    // Opening the screen used to fire eleven at once, so the last one
    // came back as a 503 the screen then tried to parse as JSON -- one banner
    // reading "Kon gegevens niet ophalen", and no data at all behind it.
    const { fetchMock, refusalCount } = gatedApi(10);
    globalThis.fetch = fetchMock;

    render(Management);

    await waitFor(() => expect(screen.getByText("12.345")).toBeTruthy());
    expect(screen.queryByText(/Kon gegevens niet ophalen/)).toBeNull();
    expect(refusalCount()).toBe(0);
  });

  it("waits out a refusal instead of blanking the screen", async () => {
    // Staying under the limit is not enough on its own: the same allowance is
    // spent by whatever else is talking to MuMa at that moment -- the player's
    // artist images, another open tab -- so a refusal can arrive however little
    // this screen asks for. It is transient by construction: the calls holding
    // the gate are round trips that finish in milliseconds.
    const { fetchMock, refusalCount } = gatedApi(2);
    globalThis.fetch = fetchMock;

    render(Management);

    await waitFor(() => expect(screen.getByText("12.345")).toBeTruthy(), { timeout: 5000 });
    expect(screen.queryByText(/Kon gegevens niet ophalen/)).toBeNull();
    expect(refusalCount()).toBeGreaterThan(0);
  });
});
