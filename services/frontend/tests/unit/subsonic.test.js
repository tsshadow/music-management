import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { get } from "svelte/store";
import {
  SUBSONIC_BAD_CREDENTIALS,
  SubsonicError,
  listOf,
  offline,
  queryString,
  subsonicJson,
  viewHasOfflineSource,
  watchConnectivity,
} from "../../src/lib/subsonic.js";
import {
  credentials,
  mumaApiKey,
  mumaSessionActive,
  mumaUser,
  subsonicToken,
} from "../../src/lib/store.js";

const BODY = { "subsonic-response": { status: "ok", tracks: { track: [{ id: "1" }] } } };
const LOCAL = { "subsonic-response": { status: "ok", tracks: { track: [{ id: "local" }] } } };

/**
 * A platform whose storage reports itself present, which is what puts the
 * switch in play at all.
 *
 * @param {object} [overrides]
 * @returns {object}
 */
function shell(overrides = {}) {
  return {
    storage: {
      supported: true,
      query: vi.fn(async () => LOCAL),
      isOffline: vi.fn(async () => false),
      onConnectivity: vi.fn(() => () => {}),
      ...overrides,
    },
  };
}

const browser = { storage: { supported: false, query: vi.fn() } };

/** A fetch that answers `body`. */
function answering(body = BODY) {
  return vi.fn(async () => ({ ok: true, json: async () => body }));
}

/** The rejection `fetch` produces when the request never reached a server. */
function unreachable() {
  return vi.fn(async () => {
    throw new TypeError("Failed to fetch");
  });
}

describe("subsonicJson", () => {
  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "user", password: "pw" });
    subsonicToken.set({ username: "user", token: "test-subsonic-token" });
    offline.set(false);
  });

  afterEach(() => {
    offline.set(false);
    vi.restoreAllMocks();
  });

  it("asks the server, with the credentials and the parameters", async () => {
    const fetchImpl = answering();

    const body = await subsonicJson(
      "getSpotifyTracks",
      { sort: "recent", count: 50 },
      { platform: browser, fetchImpl },
    );

    const url = fetchImpl.mock.calls[0][0];
    expect(url).toContain("https://lms.example/rest/getSpotifyTracks?");
    expect(url).toContain("u=user");
    expect(url).toContain("sort=recent");
    expect(url).toContain("count=50");
    expect(body).toBe(body);
    expect(body["subsonic-response"].tracks.track[0].id).toBe("1");
  });

  it("hands the body back untouched, so a caller cannot tell who answered", async () => {
    const platform = shell({ isOffline: vi.fn(async () => true) });
    offline.set(true);

    const online = await subsonicJson("getSpotifyTracks", {}, { fetchImpl: answering() });
    const local = await subsonicJson("getSpotifyTracks", {}, { platform });

    expect(Object.keys(online)).toEqual(Object.keys(local));
    expect(local["subsonic-response"].status).toBe("ok");
  });

  // A phone in a tunnel: attempting the server first is twenty seconds of
  // spinner per list, so a known-offline shell does not attempt it at all --
  // provided the device still confirms it, which is what `isOffline: true`
  // stands in for here.
  it("goes straight to the device when the shell confirms there is no route", async () => {
    const platform = shell({ isOffline: vi.fn(async () => true) });
    const fetchImpl = answering();
    offline.set(true);

    const body = await subsonicJson("getAlbumList2", { type: "newest" }, { platform, fetchImpl });

    expect(fetchImpl).not.toHaveBeenCalled();
    expect(platform.storage.query).toHaveBeenCalledWith({
      method: "getAlbumList2",
      params: { type: "newest" },
    });
    expect(body["subsonic-response"].tracks.track[0].id).toBe("local");
  });

  // The flag is a leftover from an earlier blip; the device says it can reach
  // a server again, so the stale "offline" belief clears and the request is
  // tried for real rather than being shortcut to the device forever.
  it("does not keep shortcutting to the device once the shell says the route is back", async () => {
    const platform = shell({ isOffline: vi.fn(async () => false) });
    const fetchImpl = answering();
    offline.set(true);

    const body = await subsonicJson("getGenres", {}, { platform, fetchImpl });

    expect(fetchImpl).toHaveBeenCalledOnce();
    expect(platform.storage.query).not.toHaveBeenCalled();
    expect(get(offline)).toBe(false);
    expect(body["subsonic-response"].tracks.track[0].id).toBe("1");
  });

  // The actual sticky-flag bug: `isOffline()` is advisory, so a request that
  // merely timed out on a device the shell still believes has a route must not
  // be quietly answered from the library -- that is what left the app
  // reporting "offline" until a restart on one blip.
  it("does not fall back on a failed request the device does not confirm as offline", async () => {
    const platform = shell({ isOffline: vi.fn(async () => false) });

    await expect(
      subsonicJson("getGenres", {}, { platform, fetchImpl: unreachable() }),
    ).rejects.toThrow(/Failed to fetch/);

    expect(platform.storage.query).not.toHaveBeenCalled();
    expect(get(offline)).toBe(false);
  });

  // Only once the device itself confirms it has no route does the same failed
  // request fall back and set the flag, so the next list in this screenful
  // skips the wait this one just paid for.
  it("falls back to the device, and remembers it, once offline is confirmed", async () => {
    const platform = shell({ isOffline: vi.fn(async () => true) });

    const body = await subsonicJson("getGenres", {}, { platform, fetchImpl: unreachable() });

    expect(platform.storage.query).toHaveBeenCalledOnce();
    expect(body["subsonic-response"].tracks.track[0].id).toBe("local");
    expect(get(offline)).toBe(true);
  });

  // A device that cannot even answer "am I offline" is treated as "not
  // confirmed offline" rather than crashing the caller with a second error.
  it("treats a broken connectivity check as not confirmed, and lets the error travel", async () => {
    const platform = shell({
      isOffline: vi.fn(async () => Promise.reject(new Error("no bridge"))),
    });

    await expect(
      subsonicJson("getGenres", {}, { platform, fetchImpl: unreachable() }),
    ).rejects.toThrow(/Failed to fetch/);

    expect(platform.storage.query).not.toHaveBeenCalled();
    expect(get(offline)).toBe(false);
  });

  it("keeps a browser tab exactly as it was: no fallback, the error travels", async () => {
    await expect(
      subsonicJson("getGenres", {}, { platform: browser, fetchImpl: unreachable() }),
    ).rejects.toThrow(/Failed to fetch/);
    expect(get(offline)).toBe(false);
  });

  // A 401 or a 500 is the server answering. Answering the listener's own
  // library instead would turn "your password expired" into "your library shrank".
  it("does not fall back on an HTTP status, only on a request that never arrived", async () => {
    const platform = shell();
    const fetchImpl = vi.fn(async () => ({
      ok: false,
      status: 401,
      json: async () => ({ "subsonic-response": { status: "failed" } }),
    }));

    await expect(subsonicJson("getGenres", {}, { platform, fetchImpl })).rejects.toThrow(
      SubsonicError,
    );

    expect(platform.storage.query).not.toHaveBeenCalled();
  });

  // A response that arrived but was not JSON -- a proxy's HTML error page, a
  // captive portal -- throws a `SyntaxError` out of `response.json()`. That is
  // the server answering, however badly, so it must not be classified as "no
  // route to a server" the way an actual `TypeError` from `fetch` itself is.
  it("does not fall back on a response that arrived but was not JSON", async () => {
    const platform = shell({ isOffline: vi.fn(async () => true) });
    const fetchImpl = vi.fn(async () => ({
      ok: false,
      status: 502,
      json: async () => {
        throw new SyntaxError("Unexpected token < in JSON");
      },
    }));

    await expect(subsonicJson("getGenres", {}, { platform, fetchImpl })).rejects.toThrow(
      /Unexpected token/,
    );

    expect(platform.storage.query).not.toHaveBeenCalled();
    expect(get(offline)).toBe(false);
  });

  it("lets an abort through rather than answering it from the device", async () => {
    const platform = shell();
    const abort = Object.assign(new Error("aborted"), { name: "AbortError" });

    await expect(
      subsonicJson(
        "getGenres",
        {},
        {
          platform,
          fetchImpl: vi.fn(async () => {
            throw abort;
          }),
        },
      ),
    ).rejects.toBe(abort);
    expect(platform.storage.query).not.toHaveBeenCalled();
  });

  it("answers an empty body when even the device cannot", async () => {
    const platform = shell({
      isOffline: vi.fn(async () => true),
      query: vi.fn(async () => {
        throw new Error("no room");
      }),
    });
    offline.set(true);

    const body = await subsonicJson("getGenres", {}, { platform });

    expect(body["subsonic-response"].status).toBe("ok");
    expect(listOf(body, "genres.genre")).toEqual([]);
  });
});

describe("queryString", () => {
  it("drops what nobody set", () => {
    expect(queryString({ a: 1, b: undefined, c: null, d: "", e: 0 })).toBe("a=1&e=0");
  });

  it("encodes a value that would otherwise break the query", () => {
    expect(queryString({ genre: "drum & bass" })).toBe("genre=drum%20%26%20bass");
  });
});

describe("listOf", () => {
  it("reads a list", () => {
    expect(listOf(BODY, "tracks.track")).toEqual([{ id: "1" }]);
  });

  it("wraps the single object Subsonic sends for a one-element list", () => {
    const body = { "subsonic-response": { tracks: { track: { id: "1" } } } };

    expect(listOf(body, "tracks.track")).toEqual([{ id: "1" }]);
  });

  it("is an empty list for a node that is not there", () => {
    expect(listOf({}, "tracks.track")).toEqual([]);
    expect(listOf(undefined, "a.b.c")).toEqual([]);
  });
});

describe("viewHasOfflineSource", () => {
  it.each(["songs", "sets", "albums", "artists", "genres", "labels", "starred", "downloads"])(
    "%s can be answered from the device",
    (view) => {
      expect(viewHasOfflineSource(view)).toBe(true);
    },
  );

  it.each(["genre:Hardcore", "label:Masters of Hardcore", "year:2024", "album:1", "search:x"])(
    "%s can be answered from the device",
    (view) => {
      expect(viewHasOfflineSource(view)).toBe(true);
    },
  );

  it.each(["playlists", "playlist-detail"])("%s can be answered from the device", (view) => {
    expect(viewHasOfflineSource(view)).toBe(true);
  });

  // The feeds, memories and the stats are muma endpoints with no offline answer.
  it.each([
    "memories",
    "history",
    "listening",
    "release-radar",
    "daily-mix",
    "podcasts",
    "festivals",
    "lineups",
    "lineup:Defqon.1",
    "management",
  ])("%s needs the server", (view) => {
    expect(viewHasOfflineSource(view)).toBe(false);
  });

  it("is false for anything that is not a view name", () => {
    expect(viewHasOfflineSource(undefined)).toBe(false);
  });
});

describe("watchConnectivity", () => {
  beforeEach(() => offline.set(false));
  afterEach(() => offline.set(false));

  it("does nothing in a browser tab, and still hands back an unsubscribe", () => {
    expect(() => watchConnectivity({ storage: { supported: false } })()).not.toThrow();
    expect(get(offline)).toBe(false);
  });

  it("reads the current answer once, so nothing has to guess before the first event", async () => {
    const platform = shell({ isOffline: vi.fn(async () => true) });

    watchConnectivity(platform);
    await vi.waitFor(() => expect(get(offline)).toBe(true));
  });

  it("follows the shell's connectivity event", async () => {
    let emit;
    const platform = shell({
      onConnectivity: vi.fn((handler) => {
        emit = handler;
        return () => {};
      }),
    });

    watchConnectivity(platform);
    emit({ online: false });
    expect(get(offline)).toBe(true);
    emit({ online: true });
    expect(get(offline)).toBe(false);
  });
});

/**
 * Subsonic reports failures with HTTP 200 and `status: "failed"` in the body. Returned as data,
 * every list read of it came out empty -- an expired password looked like an empty library.
 */
describe("subsonicJson - failed answers", () => {
  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "user", password: "old" });
    subsonicToken.set({ username: "user", token: "test-subsonic-token" });
    mumaApiKey.set("key-1");
    mumaSessionActive.set(true);
    mumaUser.set({ id: 1, username: "user" });
  });

  afterEach(() => {
    mumaUser.set(null);
    mumaApiKey.set("");
    mumaSessionActive.set(false);
    vi.restoreAllMocks();
  });

  /** A fetch answering a failed envelope with `code` and `message`. */
  function failing(code, message) {
    return answering({ "subsonic-response": { status: "failed", error: { code, message } } });
  }

  it("throws a SubsonicError carrying the code, instead of returning the body", async () => {
    const fetchImpl = failing(70, "Artist not found");

    const error = await subsonicJson(
      "getArtist",
      { id: "9" },
      { platform: browser, fetchImpl },
    ).catch((e) => e);

    expect(error).toBeInstanceOf(SubsonicError);
    expect(error.code).toBe(70);
    expect(error.message).toBe("Artist not found");
    // Any other error leaves the session alone.
    expect(get(credentials).username).toBe("user");
    expect(get(mumaApiKey)).toBe("key-1");
  });

  it("throws on a body without an envelope", async () => {
    await expect(
      subsonicJson("getGenres", {}, { platform: browser, fetchImpl: answering({}) }),
    ).rejects.toThrow(SubsonicError);
  });

  it("error 40 -- a wrong or expired password -- ends the session, which shows the login page", async () => {
    const fetchImpl = failing(SUBSONIC_BAD_CREDENTIALS, "Wrong username or password");

    await expect(
      subsonicJson("getGenres", {}, { platform: browser, fetchImpl }),
    ).rejects.toMatchObject({ code: 40 });

    // App.svelte renders LoginPage when neither a username nor a MuMa session is left.
    expect(get(credentials).username).toBe("");
    expect(get(credentials).password).toBe("");
    expect(get(mumaSessionActive)).toBe(false);
    expect(get(mumaApiKey)).toBe("");
    expect(get(mumaUser)).toBeNull();
    // The server address belongs to the device and survives.
    expect(get(credentials).url).toBe("https://lms.example");
  });
});
