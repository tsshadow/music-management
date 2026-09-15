import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

/**
 * Shuffle and repeat, once the queue lives on the service instead of in this
 * component: `Player.svelte` reads `platform.player.ownsQueue` once, at
 * import time, to decide which of the two it is. Every other test in this
 * suite runs the browser half, so this file exists solely to force the
 * native half -- `window.Capacitor` has to be set and `@capacitor/core`
 * mocked before `Player.svelte` (and the `platform/index.js` singleton it
 * imports) is ever loaded, which is why every import below is dynamic and
 * comes after both. A shared module registry with `player.test.js` would let
 * whichever file runs first decide the platform for both, so this lives in
 * its own file: vitest gives every test file a fresh one.
 */

/**
 * A single-event-per-name fake for a Capacitor plugin -- close enough to the
 * real bridge for the native branch to run without a WebView. `addListener`
 * records one handler per event, which is all `createCapacitorPlayer` ever
 * registers, and any method this test does not care about answers with an
 * empty object instead of throwing "not a function".
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
  // The service is the one deciding shuffle and repeat; echoing the request
  // back is what every test below overrides when it wants to check that the
  // store follows the *answer* rather than the ask.
  setMode: vi.fn(async (request) => ({ shuffle: request.shuffle, repeat: request.repeat })),
  startRadio: vi.fn(async () => ({})),
  stopRadio: vi.fn(async () => ({})),
  toggleNews: vi.fn(async () => ({})),
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
const { currentTrack, isMobile, nowPlayingOpen, playerState, playlist, radioChannel, syncMode } =
  await import("../../src/lib/store.js");
const { dismissAll } = await import("../../src/lib/notifications.js");

const FIRST = { id: "song-1", title: "Raise Your Fist", artist: "Angerfist", duration: 240 };
const SECOND = { id: "song-2", title: "Encore", artist: "Angerfist", duration: 200 };

function renderPlayer(props = {}) {
  return render(Player, { onnavigate: vi.fn(), ontoggleQueue: vi.fn(), ...props });
}

describe("Player on the native shell", () => {
  beforeEach(() => {
    playlist.set([FIRST, SECOND]);
    currentTrack.set(FIRST);
    playerState.set({ playing: false, repeat: "none", shuffle: false, volume: 50 });
    syncMode.set("off");
    radioChannel.set(null);
    isMobile.set(false);
    nowPlayingOpen.set(false);
    playerPlugin.setMode.mockClear();
    playerPlugin.startRadio.mockClear();
    playerPlugin.stopRadio.mockClear();
    playerPlugin.toggleNews.mockClear();
    playerPlugin.pause.mockClear();
    global.fetch = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    dismissAll();
  });

  it("has no <audio> element at all -- the service plays, not the WebView", () => {
    const { container } = renderPlayer();

    expect(container.querySelector("audio")).toBeNull();
  });

  it("asks the service to shuffle rather than deciding it locally", async () => {
    renderPlayer();

    await fireEvent.click(screen.getByLabelText("Shuffle"));

    expect(playerPlugin.setMode).toHaveBeenCalledWith({ shuffle: true, repeat: "none" });
  });

  it("mirrors what the service actually applied, not what was asked for", async () => {
    playerPlugin.setMode.mockResolvedValueOnce({ shuffle: false, repeat: "none" });
    renderPlayer();

    await fireEvent.click(screen.getByLabelText("Shuffle"));

    // The service refused (or the request raced a mode it had already set);
    // either way the UI must not claim shuffle is on when it is not.
    expect(get(playerState).shuffle).toBe(false);
  });

  it("cycles repeat through the service the same way", async () => {
    renderPlayer();

    await fireEvent.click(screen.getByLabelText("Herhalen"));
    expect(playerPlugin.setMode).toHaveBeenCalledWith({ shuffle: false, repeat: "all" });
    expect(get(playerState).repeat).toBe("all");

    await fireEvent.click(screen.getByLabelText("Herhalen"));
    expect(playerPlugin.setMode).toHaveBeenLastCalledWith({ shuffle: false, repeat: "one" });
    expect(get(playerState).repeat).toBe("one");
  });

  // The defect this design avoids: a shuffle trail walked in JS would disagree
  // with whatever order the service actually plays next, so pressing the
  // on-screen "next" here must not touch it at all -- it falls back to the
  // plain linear step, same as if shuffle had never been turned on.
  it("does not walk a shuffle trail for the on-screen next button", async () => {
    playerState.update((s) => ({ ...s, shuffle: true }));
    renderPlayer();

    await fireEvent.click(screen.getByLabelText("Volgende"));

    expect(get(currentTrack)).toEqual(SECOND);
  });

  // `ended` is the one event a native shell does fire -- the service reports it
  // the same as a browser's element would. Before this change the handler's
  // repeat-on-end and shuffle-next logic did not know the difference; now the
  // guard above `playNext()` inside `handleEnded` returns before either runs,
  // because the service already applied `repeat: "all"` on its own queue and a
  // second, JS-decided move would be a track skipped for one that never ended.
  it("does not repeat or shuffle-advance itself when the service reports the end of a track", async () => {
    playerState.update((s) => ({ ...s, repeat: "all", shuffle: true }));
    currentTrack.set(SECOND);
    renderPlayer();

    playerPlugin.fire("ended", { status: "ended", trackId: String(SECOND.id) });
    await Promise.resolve();

    expect(get(currentTrack)).toEqual(SECOND);
  });

  it("adopts durationchange without a command and does not advance twice on the following command", async () => {
    const third = { ...SECOND, id: "song-3" };
    playlist.set([FIRST, SECOND, third]);
    renderPlayer();
    playerPlugin.fire("durationchange", { status: "playing", trackId: SECOND.id, duration: 200 });
    await waitFor(() => expect(get(currentTrack).id).toBe(SECOND.id));
    playerPlugin.fire("command", { name: "next" });
    await Promise.resolve();
    expect(get(currentTrack).id).toBe(SECOND.id);
  });

  // Radio and the news, once the service streams and syncs either instead of
  // this component's own `<audio>` element: `Player.svelte` hands off through
  // the plugin's `startRadio`/`stopRadio`/`toggleNews` and reads the result
  // back from `state()` rather than owning any of it itself.
  describe("radio and the news", () => {
    // `createCapacitorPlayer`'s snapshot is a module-level singleton shared by every test in this
    // file, and none of the tests above reset `radioChannel`/`newsPlaying` on it -- only the
    // stores get reset in the outer `beforeEach`. Without this, whichever of these tests ran last
    // would leak its native state into the next one through a stale `onMount` read.
    afterEach(() => {
      playerPlugin.fire("timeupdate", { radioChannel: null, newsPlaying: false });
    });

    it("tunes into the only channel through the service rather than the audio element", async () => {
      global.fetch = vi.fn(async (url) => {
        if (String(url).includes("/api/radio/channels")) {
          return { ok: true, json: async () => ({ channels: [{ slug: "main", name: "Radio" }] }) };
        }
        if (String(url).includes("/api/radio/time")) {
          return { ok: true, json: async () => ({ server_time: Date.now() / 1000 }) };
        }
        return { ok: true, json: async () => ({ current: null, next: null }) };
      });
      renderPlayer();

      await fireEvent.click(screen.getByLabelText("Radio"));
      await waitFor(() => expect(get(radioChannel)).toBe("main"));

      expect(playerPlugin.startRadio).toHaveBeenCalledWith({ slug: "main" });
    });

    it("leaves radio through the service and goes silent, rather than falling into the queue", async () => {
      global.fetch = vi.fn(async (url) => {
        if (String(url).includes("/api/radio/time")) {
          return { ok: true, json: async () => ({ server_time: Date.now() / 1000 }) };
        }
        return { ok: true, json: async () => ({ current: null, next: null }) };
      });
      renderPlayer();
      // Arrive at "radio is on" the same way a real session would -- through a
      // snapshot from the service -- rather than seeding the store directly.
      playerPlugin.fire("timeupdate", { position: 1, radioChannel: "main" });
      await waitFor(() => expect(get(radioChannel)).toBe("main"));

      await fireEvent.click(screen.getByLabelText("Radio"));

      expect(playerPlugin.stopRadio).toHaveBeenCalled();
      expect(playerPlugin.pause).toHaveBeenCalled();
      expect(get(radioChannel)).toBeNull();
    });

    it("toggles the news through one call to the service", async () => {
      renderPlayer();

      await fireEvent.click(screen.getByLabelText("Nieuws van het uur"));

      expect(playerPlugin.toggleNews).toHaveBeenCalled();
    });

    // The service can start or stop either without this component asking --
    // Android Auto's browse tree, Assistant, a car button, or a WebView
    // recreated mid-channel. `state()`'s own `radioChannel`/`newsPlaying`
    // fields, read on every `timeupdate`, are how the UI notices.
    it("notices radio the service started on its own", async () => {
      global.fetch = vi.fn(async (url) => {
        if (String(url).includes("/api/radio/time")) {
          return { ok: true, json: async () => ({ server_time: Date.now() / 1000 }) };
        }
        return { ok: true, json: async () => ({ current: null, next: null }) };
      });
      renderPlayer();

      playerPlugin.fire("timeupdate", { position: 1, radioChannel: "other" });
      await waitFor(() => expect(get(radioChannel)).toBe("other"));

      // Already tuned in on the far side -- asking again would restart the stream.
      expect(playerPlugin.startRadio).not.toHaveBeenCalled();
    });

    it("notices radio the service stopped on its own", async () => {
      global.fetch = vi.fn(async (url) => {
        if (String(url).includes("/api/radio/time")) {
          return { ok: true, json: async () => ({ server_time: Date.now() / 1000 }) };
        }
        return { ok: true, json: async () => ({ current: null, next: null }) };
      });
      renderPlayer();
      playerPlugin.fire("timeupdate", { position: 1, radioChannel: "main" });
      await waitFor(() => expect(get(radioChannel)).toBe("main"));

      playerPlugin.fire("timeupdate", { position: 2, radioChannel: null });
      await waitFor(() => expect(get(radioChannel)).toBeNull());
    });
  });
});
