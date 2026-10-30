import { describe, it, expect, beforeEach, vi } from "vitest";
import { bootstrapShell, rehydrateQueue, restoreSession } from "../../src/lib/nativeSession.js";
import {
  credentials,
  currentTrack,
  mumaApiKey,
  mumaApiUrl,
  playerState,
  playlist,
  signedOut,
  subsonicToken,
  subsonicTokenProblem,
  subsonicAccess,
  authParams,
} from "../../src/lib/store.js";
import { get } from "svelte/store";
import { offline } from "../../src/lib/subsonic.js";
import { offlineMode, QUEUE_STASH_KEY } from "../../src/lib/offlineMode.js";
import { cancelQueueRestore, queueRestore } from "../../src/lib/queueRestore.js";

/**
 * The shell's boot sequence: server, session, queue.
 *
 * The third of those is the phase-1 proof -- "kill the WebView during playback,
 * reopen, and the UI is where the music is" -- and it is tested here with a
 * fake plugin state and a fake fetch rather than on a phone, because the thing
 * that can go wrong is arithmetic on a queue, not Android.
 */

/** A native platform whose plugin answers the test chooses. */
function shell({ servers, stored, state, queue, log = vi.fn() } = {}) {
  return {
    system: {
      isNative: true,
      loadServerUrl: vi.fn(async () => servers ?? { subsonic: "", mumaApi: "" }),
      credentials: vi.fn(async () => ({
        username: "",
        signedIn: false,
        mumaApiKey: "",
        ...stored,
      })),
    },
    player: {
      ownsQueue: true,
      refresh: vi.fn(async () => ({
        status: "paused",
        position: 0,
        duration: 0,
        trackId: null,
        volume: 1,
        ...state,
      })),
      queueState: vi.fn(async () => ({ index: -1, length: 0, trackIds: [], ...queue })),
    },
    diagnostics: { log },
  };
}

/** MuMa's answers for "demo-user": the login, LMS's token for the same name, and the key check. */
function mumaAnswer(url) {
  if (url.includes("/api/auth/login")) {
    return {
      ok: true,
      json: async () => ({ api_key: "own-key", user: { id: 1, username: "demo-user" } }),
    };
  }
  if (url.includes("/api/auth/subsonic-token")) {
    return {
      ok: true,
      json: async () => ({ status: "ok", username: "demo-user", token: "the-subsonic-token" }),
    };
  }
  if (url.includes("/api/auth/verify")) {
    return {
      ok: true,
      json: async () => ({ type: "user", user: { id: 1, username: "demo-user", permissions: [] } }),
    };
  }
  return null;
}

/** A fetch that answers MuMa's sign-in, `/rest/getSong` from a table, and pings with ok. */
function fakeLibrary(songs, { ping = "ok" } = {}) {
  return vi.fn(async (url) => {
    const muma = mumaAnswer(url);
    if (muma) return muma;
    if (url.includes("/rest/ping")) {
      return { json: async () => ({ "subsonic-response": { status: ping } }) };
    }
    const id = new URL(url, "https://lms.example").searchParams.get("id");
    const song = songs[id];
    return {
      ok: true,
      json: async () => ({
        "subsonic-response": song ? { status: "ok", song } : { status: "failed" },
      }),
    };
  });
}

beforeEach(() => {
  credentials.set({ url: "https://localhost", username: "" });
  mumaApiUrl.set("/muma");
  mumaApiKey.set("");
  playlist.set([]);
  currentTrack.set(null);
  playerState.set({
    playing: false,
    volume: 50,
    progress: 0,
    duration: 0,
    shuffle: false,
    repeat: "none",
  });
  signedOut.set(false);
  subsonicToken.set({ username: "", token: "" });
  subsonicTokenProblem.set("");
  global.fetch = vi.fn(async () => ({ ok: false, json: async () => ({}) }));
});

describe("bootstrapShell", () => {
  it("does nothing at all in a browser tab", async () => {
    const browser = { system: { isNative: false } };

    expect(await bootstrapShell(browser)).toEqual({
      native: false,
      signedIn: false,
      restored: 0,
      offline: false,
      queueRestored: expect.any(Promise),
    });
    expect(get(credentials).url).toBe("https://localhost");
  });

  // The page's own origin inside the shell is https://localhost, which is the
  // WebView. Anything that fetches before this has run reaches nothing.
  it("puts the phone's server into the two stores every URL is built from", async () => {
    await bootstrapShell(
      shell({ servers: { subsonic: "https://lms.example", mumaApi: "https://lms.example/muma" } }),
    );

    expect(get(credentials).url).toBe("https://lms.example");
    expect(get(mumaApiUrl)).toBe("https://lms.example/muma");
  });

  it("leaves a base the phone did not answer for alone", async () => {
    mumaApiUrl.set("/muma");

    await bootstrapShell(shell({ servers: { subsonic: "https://lms.example", mumaApi: "" } }));

    expect(get(mumaApiUrl)).toBe("/muma");
  });

  it("survives a shell that cannot answer at all", async () => {
    const broken = shell();
    broken.system.loadServerUrl = vi.fn(async () => {
      throw new Error("no bridge");
    });

    expect(await bootstrapShell(broken)).toEqual({
      native: true,
      signedIn: false,
      restored: 0,
      offline: false,
      queueRestored: expect.any(Promise),
    });
  });
});

describe("restoreSession", () => {
  /** A phone signed in as "demo-user" with key-1; `extra` overrides or adds members. */
  const phoneSession = (extra = {}) => ({
    username: "demo-user",
    signedIn: true,
    mumaApiKey: "key-1",
    ...extra,
  });

  // Bug report 106: a native sign-out that failed left the session on the phone, and the boot
  // after the logout signed straight back in with it -- "Uitloggen" did nothing.
  it("does not sign back in after a logout, whatever the phone still holds", async () => {
    global.fetch = fakeLibrary({});
    const platform = shell({ stored: phoneSession() });
    platform.system.signOut = vi.fn(async () => {});
    signedOut.set(true);

    expect(await restoreSession(platform)).toBe(false);

    expect(platform.system.credentials).not.toHaveBeenCalled();
    expect(global.fetch).not.toHaveBeenCalled();
    expect(get(credentials).username).toBe("");
    expect(get(mumaApiKey)).toBe("");
    // And the phone is asked to forget its copy once more.
    expect(platform.system.signOut).toHaveBeenCalledOnce();
  });

  it("still shows the login page after a logout when the phone cannot be cleared", async () => {
    const platform = shell({ stored: phoneSession() });
    platform.system.signOut = vi.fn(async () => {
      throw new Error("bridge gone");
    });
    vi.spyOn(console, "warn").mockImplementation(() => {});
    signedOut.set(true);

    expect(await restoreSession(platform)).toBe(false);
  });

  it("a sign-in ends the logout, so the next boot takes the phone's session again", async () => {
    global.fetch = fakeLibrary({});
    signedOut.set(true);
    const { signIn } = await import("../../src/lib/login.js");

    expect((await signIn("demo-user", "hunter2")).ok).toBe(true);

    expect(get(signedOut)).toBe(false);
  });

  // Issue #101: the phone keeps no password, so the web takes its session over with the key.
  it("takes over the phone's session with its key, without signing in or any password", async () => {
    global.fetch = vi.fn(async (url) => mumaAnswer(url));

    expect(await restoreSession(shell({ stored: phoneSession() }))).toBe(true);

    expect(get(credentials).username).toBe("demo-user");
    expect(get(credentials)).not.toHaveProperty("password");
    expect(get(mumaApiKey)).toBe("key-1");
    expect(get(subsonicToken)).toEqual({ username: "demo-user", token: "the-subsonic-token" });
    const urls = global.fetch.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.includes("/api/auth/login"))).toBe(false);
    expect(urls.some((url) => url.includes("/api/auth/verify"))).toBe(true);
  });

  // Issue #101: a key MuMa refuses is not traded for a new one with a stored password.
  it("brings the login page back when MuMa refuses the phone's key", async () => {
    global.fetch = vi.fn(async (url) =>
      url.includes("/api/auth/verify") ? { ok: false, status: 401, json: async () => ({}) } : null,
    );

    expect(await restoreSession(shell({ stored: phoneSession() }))).toBe(false);

    expect(get(credentials).username).toBe("");
    expect(get(mumaApiKey)).toBe("");
    const urls = global.fetch.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.includes("/api/auth/login"))).toBe(false);
  });

  // Signed out on the phone is not a sign-out of a session somebody started on this screen.
  it("attempts nothing when the phone is signed out and keeps a web session", async () => {
    credentials.set({ url: "https://lms.example", username: "web" });
    global.fetch = vi.fn();

    expect(
      await restoreSession(shell({ stored: { username: "demo-user", signedIn: false } })),
    ).toBe(true);
    expect(global.fetch).not.toHaveBeenCalled();
    expect(get(credentials).username).toBe("web");
  });

  it("shows the login page when the phone is signed out and the web has nothing", async () => {
    expect(await restoreSession(shell({ stored: { signedIn: false } }))).toBe(false);
  });

  it("cannot take over a phone session without a key", async () => {
    global.fetch = vi.fn();

    expect(await restoreSession(shell({ stored: phoneSession({ mumaApiKey: "" }) }))).toBe(false);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("asks nothing when the stores already hold the phone's key and a token", async () => {
    credentials.set({ url: "https://lms.example", username: "demo-user" });
    mumaApiKey.set("key-1");
    subsonicToken.set({ username: "demo-user", token: "the-subsonic-token" });
    global.fetch = vi.fn();

    expect(await restoreSession(shell({ stored: phoneSession() }))).toBe(true);
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("follows the phone to another account and drops the old account's token", async () => {
    credentials.set({ url: "https://lms.example", username: "alice" });
    mumaApiKey.set("key-1");
    subsonicToken.set({ username: "alice", token: "alices-token" });
    global.fetch = vi.fn(async (url) => mumaAnswer(url));

    expect(await restoreSession(shell({ stored: phoneSession() }))).toBe(true);

    expect(get(credentials).username).toBe("demo-user");
    expect(get(subsonicToken)).toEqual({ username: "demo-user", token: "the-subsonic-token" });
  });

  // Issue #72: without a token nothing Subsonic is requested, so the boot makes sure of one.
  it("takes over the phone's token instead of fetching one", async () => {
    credentials.set({ url: "https://lms.example", username: "demo-user" });
    mumaApiKey.set("key-1");
    global.fetch = vi.fn();

    const signedIn = await restoreSession(
      shell({
        stored: phoneSession({ subsonicToken: "the-phone-token", subsonicTokenUser: "demo-user" }),
      }),
    );

    expect(signedIn).toBe(true);
    expect(get(subsonicToken)).toEqual({ username: "demo-user", token: "the-phone-token" });
    const urls = global.fetch.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.includes("/api/auth/subsonic-token"))).toBe(false);
    expect(get(authParams)).not.toContain("p=");
  });

  it("ignores a phone token issued for another name", async () => {
    credentials.set({ url: "https://lms.example", username: "demo-user" });
    mumaApiKey.set("key-1");
    global.fetch = vi.fn(async (url) => mumaAnswer(url));

    await restoreSession(
      shell({
        stored: phoneSession({ subsonicToken: "alices-token", subsonicTokenUser: "alice" }),
      }),
    );

    expect(get(subsonicToken)).toEqual({ username: "demo-user", token: "the-subsonic-token" });
  });

  it("fetches a missing token before the queue is rebuilt, an upgrade from the password build", async () => {
    credentials.set({ url: "https://lms.example", username: "demo-user" });
    mumaApiKey.set("key-1");
    global.fetch = vi.fn(async (url) => mumaAnswer(url));

    const signedIn = await restoreSession(shell({ stored: phoneSession() }));

    expect(signedIn).toBe(true);
    expect(get(subsonicToken)).toEqual({ username: "demo-user", token: "the-subsonic-token" });
    expect(get(subsonicAccess)).toBe("ok");
    // The token fetch comes first; whatever Subsonic call follows is signed with the token.
    const urls = global.fetch.mock.calls.map(([url]) => url);
    expect(urls[0]).toContain("/api/auth/subsonic-token");
    expect(urls.every((url) => !new URL(url, "https://x").searchParams.has("p"))).toBe(true);
  });

  it("stays signed in, sends nothing and says so when the token cannot be fetched", async () => {
    credentials.set({ url: "https://lms.example", username: "demo-user" });
    mumaApiKey.set("key-1");
    global.fetch = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });

    const signedIn = await restoreSession(shell({ stored: phoneSession() }));

    expect(signedIn).toBe(true);
    expect(get(authParams)).toBe("");
    expect(get(subsonicAccess)).toBe("offline");
  });
});

describe("rehydrateQueue", () => {
  const songs = {
    1: { id: "1", title: "One", duration: 100 },
    2: { id: "2", title: "Two", duration: 200 },
    3: { id: "3", title: "Three", duration: 300 },
  };

  it("restores nothing when the service is holding nothing", async () => {
    expect(await rehydrateQueue(shell(), fakeLibrary(songs))).toBe(0);
    expect(get(playlist)).toEqual([]);
  });

  // The whole point of phase 1: the WebView died, the service kept playing.
  it("rebuilds the queue and lands on the track that is playing, at its position", async () => {
    const platform = shell({
      queue: { index: 1, length: 3, trackIds: ["1", "2", "3"] },
      state: { status: "playing", position: 84.5, duration: 200, trackId: "2", volume: 0.6 },
    });

    expect(await rehydrateQueue(platform, fakeLibrary(songs))).toBe(3);

    expect(get(playlist).map((track) => track.id)).toEqual(["1", "2", "3"]);
    expect(get(currentTrack).id).toBe("2");
    expect(get(playerState)).toMatchObject({
      playing: true,
      progress: 84.5,
      duration: 200,
      volume: 60,
    });
  });

  it("touches playback in no way at all", async () => {
    const platform = shell({
      queue: { index: 0, trackIds: ["1"] },
      state: { status: "playing", trackId: "1" },
    });

    await rehydrateQueue(platform, fakeLibrary(songs));

    expect(Object.keys(platform.player)).toEqual(["ownsQueue", "refresh", "queueState"]);
  });

  // A deleted track must not cost the listener the rest of the queue, and the
  // index has to survive it -- which is why it is matched on the playing id.
  it("drops an id the library no longer knows and still points at the right track", async () => {
    const platform = shell({
      queue: { index: 2, length: 3, trackIds: ["1", "9", "3"] },
      state: { status: "paused", trackId: "3" },
    });

    expect(await rehydrateQueue(platform, fakeLibrary(songs))).toBe(2);
    expect(get(playlist).map((track) => track.id)).toEqual(["1", "3"]);
    expect(get(currentTrack).id).toBe("3");
  });

  it("falls back to the service's index when nothing is loaded", async () => {
    const platform = shell({
      queue: { index: 2, length: 3, trackIds: ["1", "2", "3"] },
      state: { status: "paused", trackId: null },
    });

    await rehydrateQueue(platform, fakeLibrary(songs));

    expect(get(currentTrack).id).toBe("3");
  });

  it("gives up quietly when every lookup fails", async () => {
    const platform = shell({ queue: { index: 0, trackIds: ["1"] } });
    const failing = vi.fn(async () => {
      throw new Error("offline");
    });

    expect(await rehydrateQueue(platform, failing)).toBe(0);
    expect(get(playlist)).toEqual([]);
  });
});

/**
 * The boot screen says which step the shell is waiting on (docs/designs/perceived-performance/).
 * The steps themselves and their order are the ones above; these only check what is reported.
 */
describe("bootstrapShell - boot stages", () => {
  const songs = {
    1: { id: "1", title: "One", duration: 100 },
    2: { id: "2", title: "Two", duration: 200 },
  };

  it("reports connecting, signing in and the queue with a count, in that order", async () => {
    credentials.set({ url: "https://lms.example", username: "web" });
    const onStage = vi.fn();
    const platform = shell({
      stored: { username: "demo-user", signedIn: false },
      queue: { index: 0, trackIds: ["1", "2"] },
      state: { status: "paused", trackId: "1" },
    });

    await bootstrapShell(platform, fakeLibrary(songs), onStage);

    const stages = onStage.mock.calls.map(([stage]) => stage);
    expect(stages.slice(0, 3)).toEqual(["connecting", "signingIn", "restoringQueue"]);
    const counts = onStage.mock.calls.filter(([, progress]) => progress).map(([, p]) => p);
    expect(counts[0]).toEqual({ done: 0, total: 2 });
    expect(counts.at(-1)).toEqual({ done: 2, total: 2 });
  });

  it("does not announce a queue restore for a phone that is signed out", async () => {
    const onStage = vi.fn();

    await bootstrapShell(shell({ stored: { signedIn: false } }), undefined, onStage);

    expect(onStage.mock.calls.map(([stage]) => stage)).toEqual(["connecting", "signingIn"]);
  });

  it("boots all the same when showing a stage throws", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    credentials.set({ url: "https://lms.example", username: "web" });
    const onStage = vi.fn(() => {
      throw new Error("no boot screen");
    });

    const result = await bootstrapShell(shell({ stored: { signedIn: false } }), undefined, onStage);

    expect(result).toEqual({
      native: true,
      signedIn: true,
      restored: 0,
      offline: false,
      queueRestored: expect.any(Promise),
    });
  });
});

/**
 * The start-up check in the boot sequence (docs/designs/app-start-reachability/): asked before
 * the session and the queue, and only a signed-in phone that cannot reach its server stops there.
 */
describe("bootstrapShell - start-up check", () => {
  const songs = {
    1: { id: "1", title: "One", duration: 100 },
    2: { id: "2", title: "Two", duration: 200 },
    3: { id: "3", title: "Three", duration: 300 },
  };
  const signedInPhone = {
    username: "demo-user",
    signedIn: true,
    mumaApiKey: "key-1",
    subsonicToken: "tok",
    subsonicTokenUser: "demo-user",
  };

  /**
   * A shell whose storage answers the start-up check with `state`, and whose downloaded library
   * holds `downloaded` -- the offline side of `subsonicJson` reads `query`.
   */
  function shellWithStorage({
    check = "reachable",
    offlineChosen = false,
    downloaded = [],
    ...rest
  }) {
    const platform = shell(rest);
    let chosen = offlineChosen;
    platform.storage = {
      supported: true,
      checkServer: vi.fn(async () => ({ state: check, elapsedMs: 12, offlineChosen: chosen })),
      setOfflineMode: vi.fn(async (enabled) => {
        chosen = enabled;
      }),
      isOffline: vi.fn(async () => chosen),
      onConnectivity: () => () => {},
      query: vi.fn(async ({ method, params }) => {
        const song =
          method === "getSong" && downloaded.includes(params.id) ? songs[params.id] : null;
        return { "subsonic-response": song ? { status: "ok", song } : { status: "ok" } };
      }),
    };
    return platform;
  }

  beforeEach(() => {
    localStorage.clear();
    offline.set(false);
    mumaApiKey.set("key-1");
    subsonicToken.set({ username: "demo-user", token: "tok" });
    credentials.set({ url: "https://lms.example", username: "demo-user" });
  });

  it("asks nobody anything when the server answers", async () => {
    const decide = vi.fn();
    const platform = shellWithStorage({
      check: "reachable",
      stored: signedInPhone,
      queue: { index: 0, trackIds: ["1", "2"] },
    });

    const result = await bootstrapShell(platform, fakeLibrary(songs), undefined, { decide });

    expect(decide).not.toHaveBeenCalled();
    expect(result).toMatchObject({ signedIn: true, restored: 2, offline: false });
    expect(platform.diagnostics.log).toHaveBeenCalledWith(
      "shell:reachability",
      expect.objectContaining({ state: "reachable", elapsedMs: 12 }),
    );
  });

  it("goes the normal way when the server refuses the credentials", async () => {
    const decide = vi.fn();
    const platform = shellWithStorage({ check: "authFailed", stored: signedInPhone });

    const result = await bootstrapShell(platform, fakeLibrary(songs), undefined, { decide });

    expect(decide).not.toHaveBeenCalled();
    expect(result.offline).toBe(false);
  });

  it("does not ask a signed-out phone: the login page follows either way", async () => {
    const decide = vi.fn();
    const platform = shellWithStorage({ check: "unreachable", stored: { signedIn: false } });

    await bootstrapShell(platform, fakeLibrary(songs), undefined, { decide });

    expect(decide).not.toHaveBeenCalled();
  });

  it("continues online when the listener waited and the server came back", async () => {
    const platform = shellWithStorage({
      check: "unreachable",
      stored: signedInPhone,
      queue: { index: 0, trackIds: ["1", "2", "3"] },
    });
    const decide = vi.fn(async () => "online");

    const result = await bootstrapShell(platform, fakeLibrary(songs), undefined, { decide });

    expect(decide).toHaveBeenCalledWith(expect.objectContaining({ state: "unreachable" }));
    expect(result).toMatchObject({ restored: 3, offline: false });
    expect(platform.storage.setOfflineMode).not.toHaveBeenCalled();
  });

  it("restores only the downloaded tracks after Offline verder, and counts the rest", async () => {
    const platform = shellWithStorage({
      check: "unreachable",
      stored: signedInPhone,
      downloaded: ["1", "3"],
      queue: { index: 1, trackIds: ["1", "2", "3"] },
    });
    platform.player.refresh = vi.fn(async () => ({
      status: "paused",
      position: 42,
      duration: 200,
      trackId: "2",
      volume: 1,
    }));
    const fetchImpl = fakeLibrary(songs);
    const onStage = vi.fn();

    const result = await bootstrapShell(platform, fetchImpl, onStage, {
      decide: async () => "offline",
    });

    expect(result).toMatchObject({ signedIn: true, restored: 2, offline: true });
    expect(platform.storage.setOfflineMode).toHaveBeenCalledWith(true);
    expect(get(offline)).toBe(true);
    expect(get(playlist).map((track) => track.id)).toEqual(["1", "3"]);
    // Two was playing and is not on the device: the next downloaded track, from its start.
    expect(get(currentTrack).id).toBe("3");
    expect(get(playerState).progress).toBe(0);
    expect(get(offlineMode)).toMatchObject({ active: true, skipped: 1, restored: 2 });
    expect(JSON.parse(localStorage.getItem(QUEUE_STASH_KEY))).toMatchObject({
      ids: ["1", "2", "3"],
      offlineIds: ["1", "3"],
    });
    // Nothing went to the server that is not there.
    expect(fetchImpl.mock.calls.some(([url]) => String(url).includes("/rest/getSong"))).toBe(false);
    expect(onStage.mock.calls.map(([stage]) => stage)).toContain("offlineStart");
  });

  it("stays offline without asking again when the process already chose it", async () => {
    const decide = vi.fn();
    const platform = shellWithStorage({
      check: "noNetwork",
      offlineChosen: true,
      stored: signedInPhone,
    });

    const result = await bootstrapShell(platform, fakeLibrary(songs), undefined, { decide });

    expect(decide).not.toHaveBeenCalled();
    expect(result.offline).toBe(true);
  });

  it("leaves offline mode and puts the full queue back once the server is there again", async () => {
    localStorage.setItem(
      QUEUE_STASH_KEY,
      JSON.stringify({ ids: ["1", "2", "3"], playingId: "3", index: 2, offlineIds: ["1", "3"] }),
    );
    const platform = shellWithStorage({
      check: "reachable",
      offlineChosen: true,
      stored: signedInPhone,
      queue: { index: 1, trackIds: ["1", "3"] },
      state: { status: "paused", trackId: "3" },
    });
    platform.storage.checkServer = vi.fn(async () => ({
      state: "reachable",
      elapsedMs: 5,
      offlineChosen: true,
    }));

    const result = await bootstrapShell(platform, fakeLibrary(songs));

    expect(platform.storage.setOfflineMode).toHaveBeenCalledWith(false);
    expect(result).toMatchObject({ restored: 3, offline: false });
    expect(get(playlist).map((track) => track.id)).toEqual(["1", "2", "3"]);
    expect(localStorage.getItem(QUEUE_STASH_KEY)).toBeNull();
  });
});

/**
 * Issue #113: in the app the queue restore runs behind the mounted UI (`deferQueue`). These pin
 * the order -- `bootstrapShell` resolves (and the app mounts) before a single queued track has
 * been looked up -- and what a choice made meanwhile does to the restore.
 */
describe("bootstrapShell - deferred queue restore (issue #113)", () => {
  const songs = {
    1: { id: "1", title: "One", duration: 100 },
    2: { id: "2", title: "Two", duration: 200 },
    3: { id: "3", title: "Three", duration: 300 },
  };

  /** `fakeLibrary`, except that every `getSong` waits until `release()` is called. */
  function gatedLibrary() {
    let release;
    const gate = new Promise((resolve) => {
      release = resolve;
    });
    const answer = fakeLibrary(songs);
    const fetchImpl = vi.fn(async (url) => {
      if (url.includes("/rest/getSong")) await gate;
      return answer(url);
    });
    return { fetchImpl, release };
  }

  /** A phone that is signed in through the web session, holding queue 1-2-3 on track 2. */
  function signedInShell(overrides = {}) {
    credentials.set({ url: "https://lms.example", username: "demo-user" });
    subsonicToken.set({ username: "demo-user", token: "tok" });
    return shell({
      stored: { signedIn: false },
      queue: { index: 1, trackIds: ["1", "2", "3"] },
      state: { status: "playing", trackId: "2", position: 42, duration: 200 },
      ...overrides,
    });
  }

  beforeEach(() => {
    cancelQueueRestore();
    queueRestore.set({ status: "idle", done: 0, total: 0 });
  });

  it("resolves -- so the app mounts -- before the queue restore does", async () => {
    const { fetchImpl, release } = gatedLibrary();
    const onStage = vi.fn();

    const result = await bootstrapShell(signedInShell(), fetchImpl, onStage, {
      deferQueue: true,
    });

    expect(result).toMatchObject({ native: true, signedIn: true, restored: 0 });
    expect(get(queueRestore).status).toBe("restoring");
    expect(get(playlist)).toEqual([]);
    expect(get(currentTrack)).toBeNull();
    // The boot screen is gone by now; the mini player says it instead.
    expect(onStage.mock.calls.map(([stage]) => stage)).not.toContain("restoringQueue");

    release();
    expect(await result.queueRestored).toBe(3);
  });

  it("fills the queue and the playing track once the restore finishes", async () => {
    const { fetchImpl, release } = gatedLibrary();

    const result = await bootstrapShell(signedInShell(), fetchImpl, undefined, {
      deferQueue: true,
    });
    release();
    await result.queueRestored;

    expect(get(queueRestore).status).toBe("restored");
    expect(get(playlist).map((track) => track.id)).toEqual(["1", "2", "3"]);
    expect(get(currentTrack).id).toBe("2");
    expect(get(playerState)).toMatchObject({ playing: true, progress: 42 });
  });

  it("reports how far the lookups are, for the mini player", async () => {
    const { fetchImpl, release } = gatedLibrary();

    const result = await bootstrapShell(signedInShell(), fetchImpl, undefined, {
      deferQueue: true,
    });
    await vi.waitFor(() => expect(get(queueRestore).total).toBe(3));
    release();
    await result.queueRestored;

    expect(get(queueRestore)).toMatchObject({ done: 3, total: 3 });
  });

  it("is cancelled by a track the listener starts first, and never overwrites it", async () => {
    const { fetchImpl, release } = gatedLibrary();
    const chosen = { id: "99", title: "Chosen", duration: 120 };

    const result = await bootstrapShell(signedInShell(), fetchImpl, undefined, {
      deferQueue: true,
    });
    playlist.set([chosen]);
    currentTrack.set(chosen);

    expect(get(queueRestore).status).toBe("cancelled");
    release();
    expect(await result.queueRestored).toBe(0);
    expect(get(playlist)).toEqual([chosen]);
    expect(get(currentTrack)).toEqual(chosen);
  });

  it("keeps a track queued meanwhile behind the restored queue", async () => {
    const { fetchImpl, release } = gatedLibrary();
    const queued = { id: "7", title: "Queued", duration: 90 };

    const result = await bootstrapShell(signedInShell(), fetchImpl, undefined, {
      deferQueue: true,
    });
    playlist.update((tracks) => [...tracks, queued]);
    expect(get(queueRestore).status).toBe("restoring");
    release();
    await result.queueRestored;

    expect(get(playlist).map((track) => track.id)).toEqual(["1", "2", "3", "7"]);
    expect(get(currentTrack).id).toBe("2");
  });

  it("follows the service when it moved on to the next track during the lookups", async () => {
    const { fetchImpl, release } = gatedLibrary();
    const platform = signedInShell();
    platform.player.state = vi.fn(() => ({
      status: "playing",
      position: 3,
      duration: 300,
      trackId: "3",
      volume: 1,
    }));

    const result = await bootstrapShell(platform, fetchImpl, undefined, { deferQueue: true });
    release();
    await result.queueRestored;

    expect(get(currentTrack).id).toBe("3");
    expect(get(playerState).progress).toBe(3);
  });

  it("puts the previous session's queue back when the service holds none", async () => {
    const leftover = [{ id: "5", title: "Left over", duration: 60 }];
    playlist.set(leftover);
    currentTrack.set(leftover[0]);

    const result = await bootstrapShell(
      signedInShell({ queue: { index: -1, trackIds: [] }, state: { trackId: null } }),
      fakeLibrary(songs),
      undefined,
      { deferQueue: true },
    );
    await result.queueRestored;

    expect(get(queueRestore).status).toBe("restored");
    expect(get(playlist)).toEqual(leftover);
    expect(get(currentTrack)).toEqual(leftover[0]);
  });

  it("does not start a restore for a phone without a session", async () => {
    const result = await bootstrapShell(
      shell({ stored: { signedIn: false } }),
      undefined,
      undefined,
      {
        deferQueue: true,
      },
    );

    expect(result.signedIn).toBe(false);
    expect(get(queueRestore).status).toBe("idle");
    expect(await result.queueRestored).toBe(0);
  });
});
