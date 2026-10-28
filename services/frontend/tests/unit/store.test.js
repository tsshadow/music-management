import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { get } from "svelte/store";
import {
  hasPermission,
  userPermissions,
  mumaUser,
  authParams,
  credentials,
  mumaApiUrl,
  mumaApiKey,
  favoriteGenres,
  loadFrontendSettings,
  saveFrontendSetting,
  flushLocaleSave,
  flushFrontendSettings,
  homeShortcutCount,
  homeListCount,
  hydrateMumaUserFromApiKey,
  restUrl,
  subsonicToken,
  subsonicTokenQuery,
  refreshSubsonicToken,
  endRejectedSession,
  ensureSubsonicToken,
  keepSubsonicTokenFresh,
  subsonicAccess,
  subsonicTokenProblem,
  mumaSessionActive,
  signedIn,
  withoutPassword,
} from "../../src/lib/store";
import { md5 } from "../../src/lib/md5.js";
import { locale } from "../../src/lib/i18n";

describe("store - hasPermission", () => {
  beforeEach(() => {
    userPermissions.set([]);
    mumaUser.set(null);
  });

  it("should return false when user has no permissions and is not admin", () => {
    expect(hasPermission("music.read")).toBe(false);
  });

  it("should return true when user has the specific permission", () => {
    userPermissions.set(["music.read"]);
    expect(hasPermission("music.read")).toBe(true);
  });

  it("should return true when user is admin via is_admin flag", () => {
    mumaUser.set({ is_admin: true });
    expect(hasPermission("any.permission")).toBe(true);
  });

  it("should return true when user has admin role name", () => {
    mumaUser.set({ role_name: "admin" });
    expect(hasPermission("any.permission")).toBe(true);
  });

  it("should return false for other permissions if only one is granted", () => {
    userPermissions.set(["music.read"]);
    expect(hasPermission("users.read")).toBe(false);
  });
});

describe("store - authParams", () => {
  it("should return empty string when credentials are missing", () => {
    credentials.set({ username: "", password: "" });
    expect(get(authParams)).toBe("");
  });

  it("should return encoded token-signed params when a token is stored", () => {
    credentials.set({ username: "test_user", password: "test_password" });
    subsonicToken.set({ username: "test_user", token: "the-subsonic-token" });
    const params = get(authParams);
    expect(params).toContain("u=test_user");
    expect(params).toContain("t=");
    expect(params).not.toContain("p=");
    expect(params).toContain("v=1.12.0");
    expect(params).toContain("c=spotify");
  });

  it("should encode special characters in the name", () => {
    credentials.set({ username: "user@example.org", password: "pass word" });
    subsonicToken.set({ username: "user@example.org", token: "the-subsonic-token" });
    const params = get(authParams);
    expect(params).toContain("u=user%40example.org");
    expect(params).not.toContain("pass");
  });
});

/**
 * Bug report 103: with the account's Subsonic token every URL is signed with
 * `t = md5(token + salt)` and `s`, and the password is in none of them.
 */
describe("store - authParams with a Subsonic token", () => {
  beforeEach(() => {
    subsonicToken.set({ username: "", token: "" });
  });

  it("signs with the token, never the password, once one is stored for this user", () => {
    credentials.set({ username: "demo-user", password: "hunter2" });
    subsonicToken.set({ username: "demo-user", token: "the-subsonic-token" });

    const params = new URLSearchParams(get(authParams));

    expect(params.get("u")).toBe("demo-user");
    expect(params.has("p")).toBe(false);
    expect(get(authParams)).not.toContain("hunter2");
    expect(params.get("t")).toBe(md5(`the-subsonic-token${params.get("s")}`));
    expect(params.get("s")).toMatch(/^[0-9a-f]{24}$/);
  });

  it("keeps one salt per session, so the URLs a page builds stay cacheable", () => {
    credentials.set({ username: "demo-user", password: "hunter2" });
    subsonicToken.set({ username: "demo-user", token: "the-subsonic-token" });

    expect(get(authParams)).toBe(get(authParams));
  });

  it("ignores a token issued for another account -- and signs nothing at all then", () => {
    credentials.set({ username: "demo-user", password: "hunter2" });
    subsonicToken.set({ username: "alice", token: "alices-token" });

    expect(get(authParams)).toBe("");
  });

  /** Issue #72: no token, no Subsonic request -- the password is never the signature. */
  it("never puts the password in the query, with or without a token", () => {
    credentials.set({ username: "demo-user", password: "hunter2" });
    subsonicToken.set({ username: "", token: "" });
    expect(get(authParams)).toBe("");

    subsonicToken.set({ username: "demo-user", token: "the-subsonic-token" });
    expect(get(authParams)).not.toContain("p=");
    expect(get(authParams)).not.toContain("hunter2");
  });

  it("signs nothing when signed out, token or not", () => {
    credentials.set({ username: "", password: "" });
    subsonicToken.set({ username: "demo-user", token: "the-subsonic-token" });

    expect(get(authParams)).toBe("");
  });

  it("builds the query the way LMS checks it", () => {
    expect(subsonicTokenQuery("te un", "tok", "abc")).toBe(
      `u=te%20un&t=${md5("tokabc")}&s=abc&v=1.12.0&c=spotify&f=json`,
    );
  });

  it("a rejected session drops the token with the password", () => {
    credentials.set({ username: "demo-user", password: "hunter2" });
    subsonicToken.set({ username: "demo-user", token: "the-subsonic-token" });

    endRejectedSession();

    expect(get(subsonicToken)).toEqual({ username: "", token: "" });
  });
});

describe("store - refreshSubsonicToken", () => {
  beforeEach(() => {
    subsonicToken.set({ username: "", token: "" });
    mumaApiUrl.set("https://muma.example/muma");
    mumaApiKey.set("own-key");
  });

  it("asks with the user's own key and stores the answer", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: "ok", username: "demo-user", token: "the-subsonic-token" }),
    }));

    const answer = await refreshSubsonicToken(fetchImpl);

    expect(answer).toEqual({ username: "demo-user", token: "the-subsonic-token" });
    expect(get(subsonicToken)).toEqual({ username: "demo-user", token: "the-subsonic-token" });
    const [url, options] = fetchImpl.mock.calls[0];
    expect(url).toBe("https://muma.example/muma/api/auth/subsonic-token");
    expect(options.headers["X-API-Key"]).toBe("own-key");
  });

  it("a server without the endpoint leaves the stored token alone, and says try later", async () => {
    subsonicToken.set({ username: "demo-user", token: "kept" });
    const fetchImpl = vi.fn(async () => ({ ok: false, status: 404, json: async () => ({}) }));

    expect(await refreshSubsonicToken(fetchImpl)).toBe(null);
    expect(get(subsonicToken)).toEqual({ username: "demo-user", token: "kept" });
    expect(get(subsonicTokenProblem)).toBe("offline");
  });

  it("an unreachable server leaves it alone too", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error("network down");
    });

    expect(await refreshSubsonicToken(fetchImpl)).toBe(null);
    expect(get(subsonicToken)).toEqual({ username: "", token: "" });
    expect(get(subsonicTokenProblem)).toBe("offline");
  });

  it("a refused key means sign in again", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: false, status: 401, json: async () => ({}) }));

    expect(await refreshSubsonicToken(fetchImpl)).toBe(null);
    expect(get(subsonicTokenProblem)).toBe("rejected");
  });

  it("does not ask without a key, and says sign in again", async () => {
    mumaApiKey.set("");
    const fetchImpl = vi.fn();

    expect(await refreshSubsonicToken(fetchImpl)).toBe(null);
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(get(subsonicTokenProblem)).toBe("rejected");
  });

  it("adopts LMS's spelling of the signed-in name, so the token signs for it", async () => {
    credentials.set({ username: "Demo-User", password: "pw" });
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: "ok", username: "demo-user", token: "the-subsonic-token" }),
    }));

    await refreshSubsonicToken(fetchImpl);

    expect(get(credentials).username).toBe("demo-user");
    expect(get(authParams)).toContain("u=demo-user");
    expect(get(subsonicAccess)).toBe("ok");
  });

  it("an answer without a token stores nothing", async () => {
    const fetchImpl = vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: "ok", username: "demo-user" }),
    }));

    expect(await refreshSubsonicToken(fetchImpl)).toBe(null);
    expect(get(subsonicToken).token).toBe("");
  });
});

/**
 * Issue #72: a session without a token fetches one before its first Subsonic
 * request, and says why when it cannot -- instead of signing with the password.
 */
describe("store - ensureSubsonicToken and subsonicAccess", () => {
  beforeEach(() => {
    subsonicToken.set({ username: "", token: "" });
    subsonicTokenProblem.set("");
    mumaApiUrl.set("https://muma.example/muma");
    mumaApiKey.set("own-key");
    credentials.set({ username: "demo-user", password: "pw" });
  });

  const answering = (body) => vi.fn(async () => ({ ok: true, json: async () => body }));

  it("fetches a missing token and reports access once it is there", async () => {
    const fetchImpl = answering({
      status: "ok",
      username: "demo-user",
      token: "the-subsonic-token",
    });

    expect(get(subsonicAccess)).toBe("pending");
    expect(await ensureSubsonicToken(fetchImpl)).toBe(true);

    expect(get(subsonicAccess)).toBe("ok");
    expect(new URLSearchParams(get(authParams)).has("p")).toBe(false);
  });

  it("does not fetch when a token already signs for the name", async () => {
    subsonicToken.set({ username: "demo-user", token: "kept" });
    const fetchImpl = vi.fn();

    expect(await ensureSubsonicToken(fetchImpl)).toBe(true);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("concurrent callers share one fetch", async () => {
    const fetchImpl = answering({
      status: "ok",
      username: "demo-user",
      token: "the-subsonic-token",
    });

    const results = await Promise.all([
      ensureSubsonicToken(fetchImpl),
      ensureSubsonicToken(fetchImpl),
    ]);

    expect(results).toEqual([true, true]);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("an unreachable server leaves no params and an offline state", async () => {
    const fetchImpl = vi.fn(async () => {
      throw new Error("network down");
    });

    expect(await ensureSubsonicToken(fetchImpl)).toBe(false);
    expect(get(authParams)).toBe("");
    expect(get(subsonicAccess)).toBe("offline");
  });

  it("a refused account leaves no params and a sign-in-again state", async () => {
    const fetchImpl = vi.fn(async () => ({ ok: false, status: 403, json: async () => ({}) }));

    expect(await ensureSubsonicToken(fetchImpl)).toBe(false);
    expect(get(authParams)).toBe("");
    expect(get(subsonicAccess)).toBe("rejected");
  });

  it("signed out there is nothing to fetch", async () => {
    credentials.set({ username: "", password: "" });
    const fetchImpl = vi.fn();

    expect(await ensureSubsonicToken(fetchImpl)).toBe(false);
    expect(fetchImpl).not.toHaveBeenCalled();
    expect(get(subsonicAccess)).toBe("none");
  });

  it("a rejected session clears the problem with the rest", () => {
    subsonicTokenProblem.set("rejected");

    endRejectedSession();

    expect(get(subsonicTokenProblem)).toBe("");
    expect(get(subsonicAccess)).toBe("none");
  });
});

/**
 * The production cause of the password in the web shell's URLs: the token was asked for once per
 * page load, and a failed ask was never repeated while the WebView page lived on for hours.
 */
describe("store - keepSubsonicTokenFresh", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    subsonicToken.set({ username: "", token: "" });
    subsonicTokenProblem.set("");
    mumaApiUrl.set("https://muma.example/muma");
    mumaApiKey.set("own-key");
    credentials.set({ username: "demo-user", password: "pw" });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  /** How often the token endpoint was asked (the admin check that follows a token is not). */
  const tokenFetches = () =>
    globalThis.fetch.mock.calls.filter(([url]) => String(url).includes("/api/auth/subsonic-token"))
      .length;

  /** A window stand-in whose events the test fires by hand. */
  function fakeTarget() {
    const listeners = {};
    const doc = { visibilityState: "visible", listeners: {} };
    doc.addEventListener = (name, fn) => (doc.listeners[name] = fn);
    doc.removeEventListener = (name) => delete doc.listeners[name];
    return {
      document: doc,
      listeners,
      addEventListener: (name, fn) => (listeners[name] = fn),
      removeEventListener: (name) => delete listeners[name],
    };
  }

  it("asks again after a failed fetch, without a reload, and stops once a token signs", async () => {
    let answer = () => {
      throw new Error("music-manager restarting");
    };
    globalThis.fetch = vi.fn(async () => answer());
    await ensureSubsonicToken();
    expect(get(subsonicAccess)).toBe("offline");

    const stop = keepSubsonicTokenFresh({ intervalMs: 30_000, target: fakeTarget() });
    answer = () => ({
      ok: true,
      json: async () => ({ status: "ok", username: "demo-user", token: "the-subsonic-token" }),
    });
    await vi.advanceTimersByTimeAsync(30_000);

    expect(get(subsonicAccess)).toBe("ok");
    const calls = tokenFetches();
    await vi.advanceTimersByTimeAsync(90_000);
    expect(tokenFetches()).toBe(calls);
    stop();
  });

  it("asks again when the page becomes visible or the device comes back online", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ status: "ok", username: "demo-user", token: "the-subsonic-token" }),
    }));
    const target = fakeTarget();
    const stop = keepSubsonicTokenFresh({ intervalMs: 3_600_000, target });

    target.document.listeners.visibilitychange();
    await vi.advanceTimersByTimeAsync(0);
    expect(tokenFetches()).toBe(1);

    subsonicToken.set({ username: "", token: "" });
    target.listeners.online();
    await vi.advanceTimersByTimeAsync(0);
    expect(tokenFetches()).toBe(2);

    stop();
    expect(target.listeners.online).toBeUndefined();
  });

  it("does nothing while signed out", async () => {
    credentials.set({ username: "", password: "" });
    globalThis.fetch = vi.fn();
    const stop = keepSubsonicTokenFresh({ intervalMs: 1_000, target: fakeTarget() });

    await vi.advanceTimersByTimeAsync(5_000);

    expect(globalThis.fetch).not.toHaveBeenCalled();
    stop();
  });
});

describe("store - restUrl", () => {
  it("falls back to the page origin when no server is configured", () => {
    credentials.set({ url: "", username: "", password: "" });
    expect(restUrl("/rest/ping?u=x")).toBe(`${window.location.origin}/rest/ping?u=x`);
  });

  it("builds on a configured server without a trailing slash", () => {
    credentials.set({ url: "https://muma.example", username: "", password: "" });
    expect(restUrl("/rest/ping?u=x")).toBe("https://muma.example/rest/ping?u=x");
  });

  it("strips a trailing slash from the configured server so the path is not doubled", () => {
    credentials.set({ url: "https://muma.example/", username: "", password: "" });
    expect(restUrl("/rest/ping?u=x")).toBe("https://muma.example/rest/ping?u=x");
  });

  it("passes a leading-slash path and its query string through unchanged", () => {
    credentials.set({ url: "https://muma.example", username: "", password: "" });
    expect(restUrl("/rest/getCoverArt?id=42&size=300")).toBe(
      "https://muma.example/rest/getCoverArt?id=42&size=300",
    );
  });
});

describe("store - mumaApiUrl", () => {
  it("should have a default value", () => {
    const url = get(mumaApiUrl);
    expect(url).toBeDefined();
    expect(typeof url).toBe("string");
  });
});

describe("store - favoriteGenres account sync", () => {
  /**
   * Builds a fetch mock: GET calls resolve with `getSettings` (a JSON
   * string or null, mirroring the real `{ settings }` response shape), POST
   * calls just acknowledge success.
   */
  function mockFetch(getSettings = null) {
    global.fetch = vi.fn((_url, opts = {}) => {
      if ((opts.method || "GET") === "GET") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ settings: getSettings, updated_at: null }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ status: "ok" }) });
    });
  }

  beforeEach(() => {
    // Drive any previously-synced user back to logged-out first, so each
    // test starts from a clean slate regardless of test order (the sync
    // state lives in module-private variables, only reachable through the
    // public `mumaUser`/`favoriteGenres` stores).
    mumaUser.set(null);
    favoriteGenres.set([]);
    mumaApiKey.set("test-api-key");
    mockFetch(null);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("loads favorite genres from the account when a user with an id logs in", async () => {
    mockFetch(JSON.stringify({ favoriteGenres: ["Techno", "House"] }));
    mumaUser.set({ id: 42 });
    await vi.waitFor(() => expect(get(favoriteGenres)).toEqual(["Techno", "House"]));
    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/api/users/42/settings/frontend"),
      expect.objectContaining({ headers: { "X-API-Key": "test-api-key" } }),
    );
  });

  it("uploads pre-existing local favorites when the account has none saved yet", async () => {
    favoriteGenres.set(["Trance"]);
    mockFetch(null);
    mumaUser.set({ id: 7 });
    await vi.waitFor(() => {
      const postCall = fetch.mock.calls.find(([, opts]) => opts?.method === "PATCH");
      expect(postCall).toBeDefined();
    });
    const [, postOpts] = fetch.mock.calls.find(([, opts]) => opts?.method === "PATCH");
    // One write carries everything the login uploads (the language too), not one per key.
    expect(JSON.parse(postOpts.body).set).toMatchObject({
      favoriteGenres: ["Trance"],
    });
    expect(fetch.mock.calls.filter(([, opts]) => opts?.method === "PATCH")).toHaveLength(1);
    // The local value is kept, not wiped out while waiting for the upload.
    expect(get(favoriteGenres)).toEqual(["Trance"]);
  });

  it("saves changes made while logged in, debounced", async () => {
    vi.useFakeTimers();
    mumaUser.set({ id: 3 });
    await vi.advanceTimersByTimeAsync(0);
    fetch.mockClear();

    favoriteGenres.set(["Dubstep"]);
    favoriteGenres.set(["Dubstep", "DnB"]);
    await vi.advanceTimersByTimeAsync(400);

    const postCalls = fetch.mock.calls.filter(([, opts]) => opts?.method === "PATCH");
    expect(postCalls).toHaveLength(1);
    expect(JSON.parse(postCalls[0][1].body).set).toEqual({
      favoriteGenres: ["Dubstep", "DnB"],
    });
  });

  it("does not touch the backend while logged out", async () => {
    mumaUser.set(null);
    favoriteGenres.set(["Hardstyle"]);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetch).not.toHaveBeenCalled();
  });

  it("clears favorites on logout so they are not shown to the next browser user", async () => {
    mockFetch(JSON.stringify({ favoriteGenres: ["Techno"] }));
    mumaUser.set({ id: 9 });
    await vi.waitFor(() => expect(get(favoriteGenres)).toEqual(["Techno"]));

    mumaUser.set(null);
    expect(get(favoriteGenres)).toEqual([]);
  });
});

describe("store - frontend app-settings helpers", () => {
  beforeEach(() => {
    mumaUser.set(null);
    mumaApiKey.set("test-api-key");
  });

  it("returns the parsed settings blob", async () => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ settings: JSON.stringify({ language: "nl" }) }),
    }));
    expect(await loadFrontendSettings(1)).toEqual({ language: "nl" });
  });

  it("returns null when the account has no settings saved yet", async () => {
    global.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ settings: null }) }));
    expect(await loadFrontendSettings(1)).toBeNull();
  });

  it("returns null on a non-ok response", async () => {
    global.fetch = vi.fn(async () => ({ ok: false, status: 403, json: async () => ({}) }));
    expect(await loadFrontendSettings(1)).toBeNull();
  });

  it("returns null when the request rejects", async () => {
    global.fetch = vi.fn(async () => {
      throw new Error("offline");
    });
    expect(await loadFrontendSettings(1)).toBeNull();
  });

  it("returns null when the stored settings are malformed", async () => {
    global.fetch = vi.fn(async () => ({ ok: true, json: async () => ({ settings: "not json" }) }));
    expect(await loadFrontendSettings(1)).toBeNull();
  });

  it("sends only the changed key, as a PATCH, without reading the blob first", async () => {
    global.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ status: "ok" }),
    }));

    await saveFrontendSetting(5, "language", "nl");

    expect(fetch).toHaveBeenCalledTimes(1);
    const [url, opts] = fetch.mock.calls[0];
    expect(String(url)).toContain("/api/users/5/settings/frontend");
    expect(opts.method).toBe("PATCH");
    expect(JSON.parse(opts.body)).toEqual({ set: { language: "nl" } });
  });
});

describe("store - language account sync", () => {
  function mockFetch(getSettings = null) {
    global.fetch = vi.fn((_url, opts = {}) => {
      if ((opts.method || "GET") === "GET") {
        return Promise.resolve({
          ok: true,
          json: async () => ({ settings: getSettings, updated_at: null }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({ status: "ok" }) });
    });
  }

  beforeEach(() => {
    mumaUser.set(null);
    localStorage.clear();
    locale.set("en");
    mumaApiKey.set("test-api-key");
    mockFetch(null);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("applies the language stored on the account when a user logs in", async () => {
    mockFetch(JSON.stringify({ language: "nl" }));
    mumaUser.set({ id: 42 });
    await vi.waitFor(() => expect(get(locale)).toBe("nl"));
  });

  it("does not save the account language straight back to the account", async () => {
    vi.useFakeTimers();
    mockFetch(JSON.stringify({ language: "nl" }));
    mumaUser.set({ id: 42 });
    await vi.advanceTimersByTimeAsync(500);

    const languagePosts = fetch.mock.calls
      .filter(([, opts]) => opts?.method === "PATCH")
      .filter(([, opts]) => "language" in JSON.parse(opts.body).set);
    expect(languagePosts).toHaveLength(0);
  });

  it("uploads the current language when the account has none saved yet", async () => {
    locale.set("nl");
    mockFetch(null);
    mumaUser.set({ id: 7 });

    await vi.waitFor(() => {
      const post = fetch.mock.calls.find(([, opts]) => opts?.method === "PATCH");
      expect(post).toBeDefined();
    });
    const [, postOpts] = fetch.mock.calls.find(([, opts]) => opts?.method === "PATCH");
    expect(JSON.parse(postOpts.body).set.language).toBe("nl");
    expect(get(locale)).toBe("nl");
  });

  it("saves a language change made while logged in, debounced", async () => {
    vi.useFakeTimers();
    mumaUser.set({ id: 3 });
    await vi.advanceTimersByTimeAsync(500);
    fetch.mockClear();

    locale.set("nl");
    locale.set("en");
    await vi.advanceTimersByTimeAsync(400);

    const postCalls = fetch.mock.calls.filter(([, opts]) => opts?.method === "PATCH");
    expect(postCalls).toHaveLength(1);
    expect(JSON.parse(postCalls[0][1].body).set.language).toBe("en");
  });

  it("flushes a pending language save on request, and only once", async () => {
    vi.useFakeTimers();
    mumaUser.set({ id: 3 });
    await vi.advanceTimersByTimeAsync(500);
    fetch.mockClear();

    locale.set("nl");
    await flushLocaleSave();

    const posts = () => fetch.mock.calls.filter(([, opts]) => opts?.method === "PATCH");
    expect(posts()).toHaveLength(1);
    expect(JSON.parse(posts()[0][1].body).set.language).toBe("nl");

    // The debounce that was armed for the same change must not fire a second save.
    await vi.advanceTimersByTimeAsync(400);
    expect(posts()).toHaveLength(1);
  });

  it("flushing with nothing pending does not touch the backend", async () => {
    mumaUser.set({ id: 3 });
    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    fetch.mockClear();

    await flushLocaleSave();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("does not touch the backend while logged out", async () => {
    mumaUser.set(null);
    fetch.mockClear();
    locale.set("nl");
    await new Promise((resolve) => setTimeout(resolve, 500));
    expect(fetch).not.toHaveBeenCalled();
  });

  it("reverts to this browser's own language on logout", async () => {
    localStorage.setItem("muma_locale", JSON.stringify("en"));
    mockFetch(JSON.stringify({ language: "nl" }));
    mumaUser.set({ id: 9 });
    await vi.waitFor(() => expect(get(locale)).toBe("nl"));

    mumaUser.set(null);
    expect(get(locale)).toBe("en");
  });
});

describe("store - hydrateMumaUserFromApiKey", () => {
  beforeEach(() => {
    mumaUser.set(null);
    userPermissions.set([]);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("publishes the user behind an accepted key", async () => {
    mumaApiKey.set("good-key");
    const user = { id: 1, username: "demo-user", is_admin: true, permissions: ["users.read"] };
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ type: "user", user }),
    }));

    await hydrateMumaUserFromApiKey();

    expect(get(mumaUser)).toEqual(user);
    expect(get(userPermissions)).toEqual(["users.read"]);
    expect(get(mumaApiKey)).toBe("good-key");
  });

  it("drops a persisted key the server rejects", async () => {
    // A key that stays in localStorage after the backend stopped accepting it
    // (a rotated system key, an account whose key was reissued) made every
    // later call fail: nothing cleared it, and the login paths only run when
    // there is no key at all. See docker/docker-compose.yml's MUMA_API_KEY.
    mumaApiKey.set("stale-key");
    mumaUser.set({ id: 1, is_admin: true });
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 403, json: async () => ({}) }));

    await hydrateMumaUserFromApiKey();

    expect(get(mumaApiKey)).toBe("");
    expect(get(mumaUser)).toBe(null);
    expect(get(userPermissions)).toEqual([]);
  });

  // Issue #101: no password is stored to log in again with, so a refused key is the end of the
  // session and the login page comes back -- not a silent re-login.
  it("ends the session when MuMa answers 401 to the key, which shows the login page", async () => {
    credentials.set({ url: "", username: "demo-user" });
    mumaApiKey.set("revoked-key");
    mumaSessionActive.set(true);
    subsonicToken.set({ username: "demo-user", token: "the-token" });
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 401, json: async () => ({}) }));

    await hydrateMumaUserFromApiKey();

    expect(get(mumaApiKey)).toBe("");
    expect(get(credentials).username).toBe("");
    expect(get(signedIn)).toBe(false);
    const urls = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.includes("/api/auth/login"))).toBe(false);
  });

  it("keeps the key when the server is merely unreachable", async () => {
    // A network blip or a restarting backend is not evidence that the key is
    // wrong; throwing it away would log the user out of a working session.
    mumaApiKey.set("good-key");
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });

    await hydrateMumaUserFromApiKey();

    expect(get(mumaApiKey)).toBe("good-key");
  });

  it("ends the session for a leftover shared system key instead of making an admin", async () => {
    // LMS used to answer every web login with its own api-key, which MuMa
    // verifies as a system key, and startup then set `is_admin: true` for
    // whoever held it. The login now hands out the user's own key, so a system
    // key in storage is a leftover: the session goes and the user signs in once.
    credentials.set({ url: "", username: "demo-user" });
    mumaApiKey.set("lms-shared-key");
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ type: "system" }),
    }));

    await hydrateMumaUserFromApiKey();

    expect(get(mumaApiKey)).toBe("");
    expect(get(mumaUser)).toBe(null);
    expect(get(userPermissions)).toEqual([]);
    expect(get(credentials).username).toBe("");
  });

  it("keeps the key on a server error", async () => {
    mumaApiKey.set("good-key");
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }));

    await hydrateMumaUserFromApiKey();

    expect(get(mumaApiKey)).toBe("good-key");
  });
});

/**
 * The account's `frontend` blob is one JSON document written by every device on the account. It
 * used to be written whole: each save read the blob, merged its keys in and posted everything back,
 * so a phone saving in between lost its change (issue #39, bug report 116). Now only the changed
 * keys go out, as a PATCH the server merges under a row lock; the read-merge-write survives only as
 * the fallback for a server that answers the PATCH with 405.
 */
describe("store - account settings write queue", () => {
  let blob;
  let getStatus;
  let postStatus;
  let patchStatus;

  /**
   * A settings endpoint backed by `blob`: GET reads it, PATCH merges `set` into it the way the
   * server does, POST replaces it whole. Each answers with its own status.
   */
  function server() {
    global.fetch = vi.fn(async (_url, opts = {}) => {
      const method = opts.method || "GET";
      const status = { GET: getStatus, POST: postStatus, PATCH: patchStatus }[method];
      if (status !== 200) {
        return { ok: false, status, json: async () => ({ detail: "boom" }) };
      }
      if (method === "GET") {
        return { ok: true, status: 200, json: async () => ({ settings: JSON.stringify(blob) }) };
      }
      if (method === "PATCH") {
        blob = { ...blob, ...JSON.parse(opts.body).set };
        return {
          ok: true,
          status: 200,
          json: async () => ({ status: "ok", settings: JSON.stringify(blob) }),
        };
      }
      blob = JSON.parse(JSON.parse(opts.body).settings);
      return { ok: true, status: 200, json: async () => ({ status: "ok" }) };
    });
  }

  /** The calls to the settings endpoint made with `method`. */
  const calls = (method) =>
    fetch.mock.calls.filter(
      ([url, opts = {}]) =>
        String(url).includes("/users/11/settings/frontend") && (opts.method || "GET") === method,
    );

  beforeEach(async () => {
    vi.useFakeTimers();
    mumaUser.set(null);
    mumaApiKey.set("test-api-key");
    favoriteGenres.set([]);
    blob = {
      language: "en",
      homeShortcutCount: 8,
      homeListCount: 5,
      favoriteGenres: [],
      favoriteLabels: [],
      favoritePlaylists: [],
      androidOnly: "keep me",
    };
    getStatus = 200;
    postStatus = 200;
    patchStatus = 200;
    server();
    mumaUser.set({ id: 11 });
    await vi.advanceTimersByTimeAsync(500);
    fetch.mockClear();
  });

  afterEach(async () => {
    getStatus = 200;
    postStatus = 200;
    patchStatus = 200;
    await flushFrontendSettings();
    mumaUser.set(null);
    vi.useRealTimers();
  });

  it("two settings changed together go out as one PATCH carrying only those two keys", async () => {
    homeShortcutCount.set(4);
    homeListCount.set(9);
    await vi.advanceTimersByTimeAsync(400);

    expect(calls("GET")).toHaveLength(0);
    expect(calls("POST")).toHaveLength(0);
    expect(calls("PATCH")).toHaveLength(1);
    expect(JSON.parse(calls("PATCH")[0][1].body)).toEqual({
      set: { homeShortcutCount: 4, homeListCount: 9 },
    });
    expect(blob).toMatchObject({ homeShortcutCount: 4, homeListCount: 9, androidOnly: "keep me" });
  });

  it("a key another device wrote after this browser loaded the blob survives this browser's save", async () => {
    // The phone saves while the browser still holds its login-time copy.
    blob = { ...blob, androidOnly: "changed on the phone" };

    homeShortcutCount.set(4);
    await vi.advanceTimersByTimeAsync(400);

    expect(blob).toMatchObject({ homeShortcutCount: 4, androidOnly: "changed on the phone" });
  });

  it("a failed write is retried, and a newer change made meanwhile wins", async () => {
    patchStatus = 500;
    homeShortcutCount.set(2);
    await vi.advanceTimersByTimeAsync(400);
    expect(blob.homeShortcutCount).toBe(8);

    patchStatus = 200;
    homeShortcutCount.set(6);
    await vi.advanceTimersByTimeAsync(400);

    expect(blob).toMatchObject({ homeShortcutCount: 6, androidOnly: "keep me" });
  });

  it("a failed write is retried on its own after the retry delay", async () => {
    patchStatus = 503;
    homeShortcutCount.set(3);
    await vi.advanceTimersByTimeAsync(400);
    expect(blob.homeShortcutCount).toBe(8);

    patchStatus = 200;
    await vi.advanceTimersByTimeAsync(10000);

    expect(blob).toMatchObject({ homeShortcutCount: 3, androidOnly: "keep me" });
  });

  it("an explicit save goes out at once, together with what is still on its debounce", async () => {
    homeListCount.set(7);
    await saveFrontendSetting(11, "language", "nl");

    expect(calls("PATCH")).toHaveLength(1);
    expect(JSON.parse(calls("PATCH")[0][1].body)).toEqual({
      set: { homeListCount: 7, language: "nl" },
    });
    expect(blob).toMatchObject({ language: "nl", homeListCount: 7, androidOnly: "keep me" });

    // The debounce that was armed for homeListCount has nothing left to write.
    await vi.advanceTimersByTimeAsync(400);
    expect(calls("PATCH")).toHaveLength(1);
  });

  it("a server without the PATCH (405) gets the old read-merge-write instead", async () => {
    patchStatus = 405;
    homeShortcutCount.set(4);
    await vi.advanceTimersByTimeAsync(400);

    expect(calls("GET")).toHaveLength(1);
    expect(calls("POST")).toHaveLength(1);
    expect(blob).toMatchObject({ homeShortcutCount: 4, homeListCount: 5, androidOnly: "keep me" });
  });

  it("in the fallback, a failed read writes nothing and keeps the change for a retry", async () => {
    patchStatus = 405;
    getStatus = 500;
    homeShortcutCount.set(3);
    await vi.advanceTimersByTimeAsync(400);

    expect(calls("POST")).toHaveLength(0);
    expect(blob.androidOnly).toBe("keep me");

    getStatus = 200;
    await vi.advanceTimersByTimeAsync(10000);

    expect(calls("POST")).toHaveLength(1);
    expect(blob).toMatchObject({ homeShortcutCount: 3, homeListCount: 5, androidOnly: "keep me" });
  });
});

/**
 * Issue #101: builds before it persisted the password in `lms_credentials` after a sign-in. The
 * store drops it on load, and the explicit `signedIn` state no longer depends on it.
 */
describe("store - no stored password", () => {
  it("drops a password persisted by an older build and keeps the rest", () => {
    expect(
      withoutPassword({ url: "https://lms.example", username: "demo-user", password: "hunter2" }),
    ).toEqual({
      url: "https://lms.example",
      username: "demo-user",
    });
  });

  it("fills in what a stored value lacks", () => {
    expect(withoutPassword(null)).toMatchObject({ username: "" });
    expect(withoutPassword({ username: "demo-user" })).toMatchObject({ username: "demo-user" });
    expect(withoutPassword({ username: "demo-user" })).not.toHaveProperty("password");
  });

  it("rewrites localStorage without the password when the store loads", async () => {
    vi.resetModules();
    localStorage.setItem(
      "lms_credentials",
      JSON.stringify({ url: "https://lms.example", username: "demo-user", password: "hunter2" }),
    );

    const fresh = await import("../../src/lib/store.js");

    expect(get(fresh.credentials)).toEqual({ url: "https://lms.example", username: "demo-user" });
    expect(localStorage.getItem("lms_credentials")).not.toContain("hunter2");
    expect(get(fresh.signedIn)).toBe(true);
  });

  it("is signed in with a name or a MuMa session, and signed out with neither", () => {
    credentials.set({ url: "", username: "" });
    mumaSessionActive.set(false);
    expect(get(signedIn)).toBe(false);

    mumaSessionActive.set(true);
    expect(get(signedIn)).toBe(true);

    mumaSessionActive.set(false);
    credentials.set({ url: "", username: "demo-user" });
    expect(get(signedIn)).toBe(true);

    endRejectedSession();
    expect(get(signedIn)).toBe(false);
  });
});
