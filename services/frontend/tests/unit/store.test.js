import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { get, writable } from "svelte/store";
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
} from "../../src/lib/store";
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

  it("should return encoded query params when credentials are set", () => {
    credentials.set({ username: "test_user", password: "test_password" });
    const params = get(authParams);
    expect(params).toContain("u=test_user");
    expect(params).toContain("p=test_password");
    expect(params).toContain("v=1.12.0");
    expect(params).toContain("c=spotify");
  });

  it("should encode special characters in credentials", () => {
    credentials.set({ username: "user@example.com", password: "pass word" });
    const params = get(authParams);
    expect(params).toContain("u=user%40example.com");
    expect(params).toContain("p=pass%20word");
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
      const postCall = fetch.mock.calls.find(([, opts]) => opts?.method === "POST");
      expect(postCall).toBeDefined();
    });
    const [, postOpts] = fetch.mock.calls.find(([, opts]) => opts?.method === "POST");
    // One write carries everything the login uploads (the language too), not one per key.
    expect(JSON.parse(JSON.parse(postOpts.body).settings)).toMatchObject({
      favoriteGenres: ["Trance"],
    });
    expect(fetch.mock.calls.filter(([, opts]) => opts?.method === "POST")).toHaveLength(1);
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

    const postCalls = fetch.mock.calls.filter(([, opts]) => opts?.method === "POST");
    expect(postCalls).toHaveLength(1);
    expect(JSON.parse(JSON.parse(postCalls[0][1].body).settings)).toEqual({
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

  it("preserves unrelated keys when saving one setting", async () => {
    global.fetch = vi.fn(async (_url, opts = {}) => {
      if ((opts.method || "GET") === "GET") {
        return {
          ok: true,
          json: async () => ({ settings: JSON.stringify({ favoriteGenres: ["Techno"] }) }),
        };
      }
      return { ok: true, json: async () => ({ status: "ok" }) };
    });

    await saveFrontendSetting(5, "language", "nl");

    const [, postOpts] = fetch.mock.calls.find(([, opts]) => opts?.method === "POST");
    expect(JSON.parse(JSON.parse(postOpts.body).settings)).toEqual({
      favoriteGenres: ["Techno"],
      language: "nl",
    });
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
      .filter(([, opts]) => opts?.method === "POST")
      .filter(([, opts]) => "language" in JSON.parse(JSON.parse(opts.body).settings));
    expect(languagePosts).toHaveLength(0);
  });

  it("uploads the current language when the account has none saved yet", async () => {
    locale.set("nl");
    mockFetch(null);
    mumaUser.set({ id: 7 });

    await vi.waitFor(() => {
      const post = fetch.mock.calls.find(([, opts]) => opts?.method === "POST");
      expect(post).toBeDefined();
    });
    const [, postOpts] = fetch.mock.calls.find(([, opts]) => opts?.method === "POST");
    expect(JSON.parse(JSON.parse(postOpts.body).settings).language).toBe("nl");
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

    const postCalls = fetch.mock.calls.filter(([, opts]) => opts?.method === "POST");
    expect(postCalls).toHaveLength(1);
    expect(JSON.parse(JSON.parse(postCalls[0][1].body).settings).language).toBe("en");
  });

  it("flushes a pending language save on request, and only once", async () => {
    vi.useFakeTimers();
    mumaUser.set({ id: 3 });
    await vi.advanceTimersByTimeAsync(500);
    fetch.mockClear();

    locale.set("nl");
    await flushLocaleSave();

    const posts = () => fetch.mock.calls.filter(([, opts]) => opts?.method === "POST");
    expect(posts()).toHaveLength(1);
    expect(JSON.parse(JSON.parse(posts()[0][1].body).settings).language).toBe("nl");

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
    const user = { id: 1, username: "user", is_admin: true, permissions: ["users.read"] };
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
    credentials.set({ url: "", username: "user", password: "pw" });
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
    expect(get(credentials).password).toBe("");
  });

  it("keeps the key on a server error", async () => {
    mumaApiKey.set("good-key");
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }));

    await hydrateMumaUserFromApiKey();

    expect(get(mumaApiKey)).toBe("good-key");
  });
});

/**
 * The account's `frontend` blob is one JSON document and the server only takes it whole. Each key
 * used to do its own debounced read-modify-write, so two keys changed together raced and the last
 * write dropped the other's change; and a failed read (answered as `null`) made the save write a
 * blob holding only the one key, wiping every other setting -- the Android app's included.
 */
describe("store - account settings write queue", () => {
  let blob;
  let getStatus;
  let postStatus;

  /** A settings endpoint backed by `blob`, answering GET with `getStatus` and POST with `postStatus`. */
  function server() {
    global.fetch = vi.fn(async (_url, opts = {}) => {
      if ((opts.method || "GET") === "GET") {
        if (getStatus !== 200) {
          return { ok: false, status: getStatus, json: async () => ({ detail: "boom" }) };
        }
        return { ok: true, status: 200, json: async () => ({ settings: JSON.stringify(blob) }) };
      }
      if (postStatus !== 200) {
        return { ok: false, status: postStatus, json: async () => ({ detail: "boom" }) };
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
    server();
    mumaUser.set({ id: 11 });
    await vi.advanceTimersByTimeAsync(500);
    fetch.mockClear();
  });

  afterEach(async () => {
    getStatus = 200;
    postStatus = 200;
    await flushFrontendSettings();
    mumaUser.set(null);
    vi.useRealTimers();
  });

  it("two settings changed together are read once, written once, and both kept", async () => {
    homeShortcutCount.set(4);
    homeListCount.set(9);
    await vi.advanceTimersByTimeAsync(400);

    expect(calls("GET")).toHaveLength(1);
    expect(calls("POST")).toHaveLength(1);
    expect(blob).toMatchObject({ homeShortcutCount: 4, homeListCount: 9, androidOnly: "keep me" });
  });

  it("a failed read writes nothing, keeps the change, and retries it later", async () => {
    getStatus = 500;
    homeShortcutCount.set(3);
    await vi.advanceTimersByTimeAsync(400);

    expect(calls("GET")).toHaveLength(1);
    expect(calls("POST")).toHaveLength(0);
    expect(blob.androidOnly).toBe("keep me");

    getStatus = 200;
    await vi.advanceTimersByTimeAsync(10000);

    expect(calls("POST")).toHaveLength(1);
    expect(blob).toMatchObject({ homeShortcutCount: 3, homeListCount: 5, androidOnly: "keep me" });
  });

  it("a failed write is retried, and a newer change made meanwhile wins", async () => {
    postStatus = 500;
    homeShortcutCount.set(2);
    await vi.advanceTimersByTimeAsync(400);
    expect(blob.homeShortcutCount).toBe(8);

    postStatus = 200;
    homeShortcutCount.set(6);
    await vi.advanceTimersByTimeAsync(400);

    expect(blob).toMatchObject({ homeShortcutCount: 6, androidOnly: "keep me" });
  });

  it("an explicit save goes out at once, merged with what is still on its debounce", async () => {
    homeListCount.set(7);
    await saveFrontendSetting(11, "language", "nl");

    expect(calls("POST")).toHaveLength(1);
    expect(blob).toMatchObject({ language: "nl", homeListCount: 7, androidOnly: "keep me" });

    // The debounce that was armed for homeListCount has nothing left to write.
    await vi.advanceTimersByTimeAsync(400);
    expect(calls("POST")).toHaveLength(1);
  });
});
