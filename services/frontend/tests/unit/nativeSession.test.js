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
} from "../../src/lib/store.js";
import { get } from "svelte/store";

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
        password: "",
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

/** A fetch that answers `/rest/getSong` from a table and pings with ok. */
function fakeLibrary(songs, { ping = "ok" } = {}) {
  return vi.fn(async (url) => {
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
  credentials.set({ url: "https://localhost", username: "", password: "" });
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
  global.fetch = vi.fn(async () => ({ ok: false, json: async () => ({}) }));
});

describe("bootstrapShell", () => {
  it("does nothing at all in a browser tab", async () => {
    const browser = { system: { isNative: false } };

    expect(await bootstrapShell(browser)).toEqual({
      native: false,
      signedIn: false,
      restored: 0,
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

    expect(await bootstrapShell(broken)).toEqual({ native: true, signedIn: false, restored: 0 });
  });
});

describe("restoreSession", () => {
  // Bug report 106: a native sign-out that failed left the password on the phone, and the boot
  // after the logout signed straight back in with it -- "Uitloggen" did nothing.
  it("does not sign back in after a logout, whatever the phone still holds", async () => {
    global.fetch = fakeLibrary({});
    const platform = shell({
      stored: { username: "user", password: "hunter2", mumaApiKey: "key-1" },
    });
    platform.system.signOut = vi.fn(async () => {});
    signedOut.set(true);

    expect(await restoreSession(platform)).toBe(false);

    expect(platform.system.credentials).not.toHaveBeenCalled();
    expect(global.fetch).not.toHaveBeenCalled();
    expect(get(credentials).password).toBe("");
    expect(get(mumaApiKey)).toBe("");
    // And the phone is asked to forget its copy once more.
    expect(platform.system.signOut).toHaveBeenCalledOnce();
  });

  it("still shows the login page after a logout when the phone cannot be cleared", async () => {
    const platform = shell({ stored: { username: "user", password: "hunter2" } });
    platform.system.signOut = vi.fn(async () => {
      throw new Error("bridge gone");
    });
    vi.spyOn(console, "warn").mockImplementation(() => {});
    signedOut.set(true);

    expect(await restoreSession(platform)).toBe(false);
  });

  it("a sign-in ends the logout, so the next boot signs in silently again", async () => {
    global.fetch = fakeLibrary({});
    signedOut.set(true);
    const { signIn } = await import("../../src/lib/login.js");

    expect((await signIn("user", "hunter2")).ok).toBe(true);

    expect(get(signedOut)).toBe(false);
  });

  // Bug report 074: a phone that stored "Teun" for the account "user" signed
  // every Subsonic call with it, and LMS created a second user for that spelling.
  it("writes the account's own spelling back to a phone that stored another case", async () => {
    global.fetch = vi.fn(async (url) => {
      if (url.includes("/api/auth/login")) {
        return {
          ok: true,
          json: async () => ({ api_key: "own-key", user: { id: 1, username: "user" } }),
        };
      }
      return { json: async () => ({ "subsonic-response": { status: "ok" } }) };
    });
    const platform = shell({ stored: { username: "Teun", password: "hunter2" } });
    platform.system.saveCredentials = vi.fn(async () => {});

    expect(await restoreSession(platform)).toBe(true);

    expect(get(credentials).username).toBe("user");
    expect(platform.system.saveCredentials).toHaveBeenCalledWith({
      username: "user",
      password: "hunter2",
    });
  });

  it("leaves the phone alone when it already stored the account's own spelling", async () => {
    global.fetch = vi.fn(async (url) => {
      if (url.includes("/api/auth/login")) {
        return {
          ok: true,
          json: async () => ({ api_key: "own-key", user: { id: 1, username: "user" } }),
        };
      }
      return { json: async () => ({ "subsonic-response": { status: "ok" } }) };
    });
    const platform = shell({ stored: { username: "user", password: "hunter2" } });
    platform.system.saveCredentials = vi.fn(async () => {});

    expect(await restoreSession(platform)).toBe(true);
    expect(platform.system.saveCredentials).not.toHaveBeenCalled();
  });

  it("signs in silently with what the phone stored", async () => {
    global.fetch = fakeLibrary({});

    const signedIn = await restoreSession(
      shell({ stored: { username: "user", password: "hunter2", mumaApiKey: "key-1" } }),
    );

    expect(signedIn).toBe(true);
    expect(get(credentials).username).toBe("user");
    expect(get(credentials).password).toBe("hunter2");
    expect(get(mumaApiKey)).toBe("key-1");
  });

  // Blank is how the native app says "logged out". It is not a sign-out of a
  // session somebody started on this screen.
  it("attempts nothing on a blank password and keeps a web session", async () => {
    credentials.set({ url: "https://lms.example", username: "web", password: "typed" });
    global.fetch = vi.fn();

    expect(await restoreSession(shell({ stored: { username: "user", password: "" } }))).toBe(true);
    expect(global.fetch).not.toHaveBeenCalled();
    expect(get(credentials).username).toBe("web");
  });

  it("shows the login page when the phone is logged out and the web has nothing", async () => {
    expect(await restoreSession(shell({ stored: { password: "" } }))).toBe(false);
  });

  it("does not sign in again when the stores already hold the same pair", async () => {
    credentials.set({ url: "https://lms.example", username: "user", password: "hunter2" });
    global.fetch = vi.fn();

    expect(await restoreSession(shell({ stored: { username: "user", password: "hunter2" } }))).toBe(
      true,
    );
    expect(global.fetch).not.toHaveBeenCalled();
  });

  it("reports a refused password rather than pretending to be signed in", async () => {
    global.fetch = fakeLibrary({}, { ping: "failed" });

    expect(await restoreSession(shell({ stored: { username: "user", password: "wrong" } }))).toBe(
      false,
    );
    expect(get(credentials).username).toBe("");
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
