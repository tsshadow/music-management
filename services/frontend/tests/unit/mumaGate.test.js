import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  GATE_RETRY_DELAYS_MS,
  MAX_PARALLEL_MUMA_CALLS,
  MAX_PARALLEL_DIRECT_CALLS,
  gatedFetch,
  mumaCallsInFlight,
  resetMumaGate,
  withMumaGate,
} from "../../src/lib/mumaGate.js";
import { fetchMumaJson } from "../../src/lib/mumaApi.js";
import { fetchGenreTints } from "../../src/lib/genreTints.js";
import { imageLoads } from "../../src/lib/dailyMixes.js";
import {
  hydrateMumaUserFromApiKey,
  loadFrontendSettings,
  mumaApiKey,
} from "../../src/lib/store.js";

/**
 * The MuMa API as it is really reached: through the LMS proxy, which refuses
 * anything past its concurrency gate with a bare 503. `limit` is that gate --
 * four on production, half of an eight-thread pool.
 */
function gatedApi(limit, body = {}) {
  let inFlight = 0;
  let peak = 0;
  let refusals = 0;

  const fetchMock = vi.fn(async () => {
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
    peak = Math.max(peak, inFlight);
    try {
      await new Promise((resolve) => setTimeout(resolve, 1));
      return { ok: true, status: 200, json: async () => body };
    } finally {
      inFlight -= 1;
    }
  });

  return { fetchMock, peak: () => peak, refusals: () => refusals };
}

describe("the MuMa call gate", () => {
  beforeEach(() => {
    resetMumaGate();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    resetMumaGate();
  });

  it("keeps a dozen calls from as many callers under production's gate", async () => {
    // What opening the home screen does: every module fires its own batch,
    // each within its own limit, and together they used to blow through the
    // proxy's four. The cap has to count across all of them.
    const api = gatedApi(4);
    globalThis.fetch = api.fetchMock;

    const bodies = await Promise.all(
      Array.from({ length: 12 }, (_, i) =>
        fetchMumaJson(`https://muma.example/api/admin/thing/${i}`),
      ),
    );

    expect(bodies).toHaveLength(12);
    expect(api.peak()).toBeLessThanOrEqual(MAX_PARALLEL_MUMA_CALLS);
    expect(api.refusals()).toBe(0);
    expect(mumaCallsInFlight()).toBe(0);
  });

  it("hands a freed slot straight to the next waiter", async () => {
    // Releasing and letting the waiter re-acquire would let a newcomer slip in
    // between and push the count one past the cap.
    let running = 0;
    let peak = 0;
    const work = () =>
      withMumaGate(async () => {
        running += 1;
        peak = Math.max(peak, running);
        await new Promise((resolve) => setTimeout(resolve, 1));
        running -= 1;
      });

    const first = Array.from({ length: MAX_PARALLEL_MUMA_CALLS + 2 }, work);
    await new Promise((resolve) => setTimeout(resolve, 0));
    const late = Array.from({ length: 3 }, work);
    await Promise.all([...first, ...late]);

    expect(peak).toBe(MAX_PARALLEL_MUMA_CALLS);
    expect(mumaCallsInFlight()).toBe(0);
  });

  it("frees the slot when the call throws", async () => {
    await expect(withMumaGate(() => Promise.reject(new Error("network down")))).rejects.toThrow(
      "network down",
    );
    expect(mumaCallsInFlight()).toBe(0);
  });

  it("waits out a refusal from a gate someone else filled", async () => {
    // Staying under the cap is not enough on its own: the allowance is shared
    // with the player and other tabs, so a refusal can still arrive. It is
    // transient by construction, so it is retried rather than reported.
    const api = gatedApi(1, { fine: true });
    globalThis.fetch = api.fetchMock;

    const bodies = await Promise.all(
      Array.from({ length: 3 }, () => fetchMumaJson("https://muma.example/api/admin/thing")),
    );

    expect(bodies).toEqual([{ fine: true }, { fine: true }, { fine: true }]);
    expect(api.refusals()).toBeGreaterThan(0);
  });

  it("returns the last refusal when every retry is refused", async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) }));
    vi.useFakeTimers();

    const pending = gatedFetch("https://muma.example/api/admin/thing");
    await vi.runAllTimersAsync();
    const response = await pending;
    vi.useRealTimers();

    expect(response.status).toBe(503);
    expect(globalThis.fetch).toHaveBeenCalledTimes(GATE_RETRY_DELAYS_MS.length + 1);
  });

  it("waits as long as a refusal's Retry-After says, not the ladder", async () => {
    // The proxy's own refusals say when to come back; a 503 from further
    // upstream carries no header and gets the ladder.
    let calls = 0;
    globalThis.fetch = vi.fn(async () => {
      calls += 1;
      if (calls === 1) {
        return { ok: false, status: 503, headers: new Headers({ "Retry-After": "2" }) };
      }
      return { ok: true, status: 200, headers: new Headers(), json: async () => ({}) };
    });
    vi.useFakeTimers();
    vi.spyOn(Math, "random").mockReturnValue(0);

    const pending = gatedFetch("https://muma.example/api/admin/thing");
    await vi.advanceTimersByTimeAsync(1999);
    expect(calls).toBe(1);
    await vi.advanceTimersByTimeAsync(1);
    const response = await pending;
    vi.useRealTimers();

    expect(response.status).toBe(200);
    expect(calls).toBe(2);
  });

  it.each([
    "/muma/api/admin/settings",
    "/muma/api/artists/name/image?auth=x",
    "/custom/base/api/artists/artist-123",
    "/api/artists/123",
    "/muma/api/tracks/track-1/refresh",
    "https://example.test/custom/users/1",
  ])("keeps LMS-owned route %s in the proxy lane", async (url) => {
    const api = gatedApi(4);
    globalThis.fetch = api.fetchMock;
    await Promise.all(Array.from({ length: 6 }, () => gatedFetch(url)));
    expect(api.peak()).toBe(MAX_PARALLEL_MUMA_CALLS);
    expect(api.refusals()).toBe(0);
  });

  it("does not hold direct requests behind a full proxy lane", async () => {
    const releases = [];
    const held = Array.from({ length: 3 }, () =>
      withMumaGate(() => new Promise((resolve) => releases.push(resolve))),
    );
    globalThis.fetch = vi.fn(async () => ({ ok: true, status: 200 }));
    await expect(gatedFetch("/muma/api/feeds")).resolves.toMatchObject({ ok: true });
    releases.forEach((resolve) => resolve());
    await Promise.all(held);
  });

  it("sends the login down the direct lane, since nginx sends it to MuMa", async () => {
    const releases = [];
    const held = Array.from({ length: 3 }, () =>
      withMumaGate(() => new Promise((resolve) => releases.push(resolve))),
    );
    globalThis.fetch = vi.fn(async () => ({ ok: true, status: 200 }));
    await expect(gatedFetch("/muma/api/auth/login")).resolves.toMatchObject({ ok: true });
    releases.forEach((resolve) => resolve());
    await Promise.all(held);
  });

  it("caps the direct lane at eight calls", async () => {
    const api = gatedApi(8);
    globalThis.fetch = api.fetchMock;
    await Promise.all(
      Array.from({ length: 20 }, () => gatedFetch("/configured/base/api/feeds/daily-mix-soft")),
    );
    expect(api.peak()).toBe(MAX_PARALLEL_DIRECT_CALLS);
    expect(api.refusals()).toBe(0);
    expect(mumaCallsInFlight()).toBe(0);
  });

  it("takes the boot-time calls through the same gate", async () => {
    // The session check, the account settings and the genre tints used to be
    // bare `fetch` calls beside the feeds, so the home screen's first burst
    // counted past the cap however careful the feed loaders were.
    mumaApiKey.set("key-1");
    const api = gatedApi(9, { type: "user", user: { id: 1, username: "user" }, settings: null });
    globalThis.fetch = api.fetchMock;

    await Promise.all([
      hydrateMumaUserFromApiKey(),
      loadFrontendSettings(1),
      fetchGenreTints(),
      imageLoads("https://muma.example/api/artists/x/image"),
      ...Array.from({ length: 6 }, (_, i) => fetchMumaJson(`https://muma.example/api/feeds/${i}`)),
    ]);

    expect(api.peak()).toBeLessThanOrEqual(MAX_PARALLEL_DIRECT_CALLS + 1);
    expect(api.refusals()).toBe(0);
  });
});
