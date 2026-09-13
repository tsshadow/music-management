import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

/**
 * Sets-mode ±30 s and resume on the native shell: the ±30 s buttons go
 * through `platform.player.seek`/`state()` exactly like the browser engine
 * (`playerSetsMode.test.js`), but through the `MumaPlayer` plugin instead of
 * an `<audio>` element. Same reason this lives in its own file as
 * `playerNativeMode.test.js`: `window.Capacitor` and the mocked
 * `@capacitor/core` have to be in place before `Player.svelte` is ever
 * imported.
 */

function fakePlugin(overrides = {}) {
  const handlers = new Map();
  const base = {
    addListener(event, handler) {
      handlers.set(event, handler);
      return { remove: () => handlers.delete(event) };
    },
    fire(event, payload) {
      handlers.get(event)?.(payload);
    },
    ...overrides,
  };
  return new Proxy(base, {
    get(target, prop) {
      if (prop in target) return target[prop];
      return async () => ({});
    },
  });
}

const playerPlugin = fakePlugin({
  seek: vi.fn(async () => ({})),
  pause: vi.fn(async () => ({})),
});

const plugins = {
  MumaPlayer: playerPlugin,
  MumaStorage: fakePlugin(),
  MumaSpeech: fakePlugin(),
  MumaDiagnostics: fakePlugin(),
  MumaSystem: fakePlugin(),
};

vi.mock("@capacitor/core", () => ({
  registerPlugin: (name) => plugins[name],
}));

window.Capacitor = { isNativePlatform: () => true };

const { default: Player } = await import("../../src/lib/Player.svelte");
const {
  currentTrack,
  isMobile,
  mumaApiKey,
  mumaUser,
  nowPlayingOpen,
  playerState,
  playlist,
  radioChannel,
  syncMode,
} = await import("../../src/lib/store.js");
const { dismissAll, notifications } = await import("../../src/lib/notifications.js");

const SET = { id: "set-1", title: "Defqon Set", artist: "Angerfist", duration: 7200 };

function mockFetch(settingsBlob = null) {
  global.fetch = vi.fn((url, opts = {}) => {
    const method = opts.method || "GET";
    if (String(url).includes("/settings/frontend")) {
      if (method === "GET") {
        return Promise.resolve({ ok: true, json: async () => ({ settings: settingsBlob }) });
      }
      return Promise.resolve({ ok: true, json: async () => ({ status: "ok" }) });
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok" } }),
    });
  });
}

function renderPlayer(props = {}) {
  return render(Player, { onnavigate: vi.fn(), ontoggleQueue: vi.fn(), ...props });
}

describe("Player in sets mode on the native shell", () => {
  beforeEach(() => {
    playlist.set([SET]);
    currentTrack.set(SET);
    playerState.set({ playing: false, repeat: "none", shuffle: false, volume: 50 });
    syncMode.set("off");
    radioChannel.set(null);
    isMobile.set(false);
    nowPlayingOpen.set(false);
    mumaUser.set(null);
    mumaApiKey.set("");
    mockFetch(null);
    playerPlugin.seek.mockClear();
    playerPlugin.pause.mockClear();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    dismissAll();
  });

  it("shows ±30 s buttons for a set", () => {
    renderPlayer();

    expect(screen.getByLabelText("30 seconden terug")).toBeTruthy();
    expect(screen.getByLabelText("30 seconden verder")).toBeTruthy();
  });

  it("skips back through the plugin, from the service's own position", async () => {
    renderPlayer();
    playerPlugin.fire("timeupdate", { position: 500, duration: 7200 });

    await fireEvent.click(screen.getByLabelText("30 seconden terug"));

    expect(playerPlugin.seek).toHaveBeenCalledWith({ seconds: 470 });
  });

  it("skips forward through the plugin", async () => {
    renderPlayer();
    playerPlugin.fire("timeupdate", { position: 500, duration: 7200 });

    await fireEvent.click(screen.getByLabelText("30 seconden verder"));

    expect(playerPlugin.seek).toHaveBeenCalledWith({ seconds: 530 });
  });

  it("resumes a set through the plugin on play, same as the browser engine", async () => {
    mockFetch(JSON.stringify({ setResume: { "track:set-1": { position: 900, updatedAt: 1 } } }));
    mumaUser.set({ id: 7 });
    renderPlayer();

    playerPlugin.fire("play", { status: "playing", position: 0, duration: 7200 });

    await waitFor(() => expect(playerPlugin.seek).toHaveBeenCalledWith({ seconds: 900 }));
    await waitFor(() => expect(get(notifications).length).toBeGreaterThan(0));
  });
});
