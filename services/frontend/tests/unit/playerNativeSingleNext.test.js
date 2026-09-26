import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import { get } from "svelte/store";

/**
 * Bug report 108: "the next button seems to stop playback", reported on a tablet running the app.
 *
 * Pins what one tap on next does on a native shell, on every layout the tablet can show: the
 * desktop-style bar, the phone mini player (`isMobile`, which a coarse pointer makes true at any
 * width -- see bug report 090) and the full-screen Now Playing. The web player's whole part in a
 * skip is one `next` intent to the service (bug report 095); it must never answer the move it
 * then hears about with a `pause`, a `stop`, a queue replacement or a load, and its play/pause
 * state has to end up where the service's is.
 *
 * The fake reports a skip the way the real plugin does, taken from a device log: Media3 masks the
 * seek, so the first state after it already names the new item with `status: "loading"` and
 * `isPlaying` false -- a `durationchange` and `command: next`, then `pause` and `command: pause`
 * when the player was playing -- and the `play` pair follows once the new item has buffered. A
 * paused player stays paused: no `play` ever comes.
 *
 * Its own file for the same reason as `playerNativeMode.test.js`: `Player.svelte` reads
 * `platform.player.ownsQueue` once, at import time.
 */

/** How long the fake takes to "buffer" the new item, in ms of real time. */
const BUFFERING_MS = 20;

const native = { ids: [], index: -1, playing: true, calls: [] };

const handlers = new Map();

function snapshot(status) {
  return {
    status,
    position: 0,
    duration: 200,
    trackId: native.ids[native.index] ?? null,
    queueIndex: native.index,
    queueLength: native.ids.length,
  };
}

function settledStatus() {
  return native.playing ? "playing" : "paused";
}

function fire(event, payload) {
  handlers.get(event)?.(payload);
}

/** Every call the web player makes on the service, in order. */
function record(name) {
  native.calls.push(name);
  return {};
}

const playerPlugin = new Proxy(
  {
    addListener(event, handler) {
      handlers.set(event, handler);
      return { remove: () => handlers.delete(event) };
    },
    queueState: vi.fn(async () => ({
      index: native.index,
      length: native.ids.length,
      trackIds: native.ids.slice(),
    })),
    state: vi.fn(async () => snapshot(settledStatus())),
    setQueue: vi.fn(async () => {
      record("setQueue");
      return { index: native.index, length: native.ids.length, trackIds: native.ids.slice() };
    }),
    load: vi.fn(async () => record("load")),
    play: vi.fn(async () => record("play")),
    pause: vi.fn(async () => record("pause")),
    stop: vi.fn(async () => record("stop")),
    next: vi.fn(async () => {
      record("next");
      if (native.index + 1 >= native.ids.length) return {};
      native.index += 1;
      const wasPlaying = native.playing;
      const masked = snapshot("loading");
      setTimeout(() => {
        fire("durationchange", masked);
        fire("command", { name: "next" });
        if (wasPlaying) {
          fire("pause", masked);
          fire("command", { name: "pause" });
        }
      }, 0);
      setTimeout(() => {
        const ready = snapshot(settledStatus());
        if (wasPlaying) {
          fire("play", ready);
          fire("command", { name: "play" });
        }
        fire("timeupdate", ready);
      }, BUFFERING_MS);
      return {};
    }),
  },
  {
    get(target, prop) {
      if (prop in target) return target[prop];
      return async () => ({});
    },
  },
);

function quietPlugin() {
  return new Proxy(
    { addListener: () => ({ remove() {} }) },
    {
      get(target, prop) {
        if (prop in target) return target[prop];
        return async () => ({});
      },
    },
  );
}

const plugins = {
  MumaPlayer: playerPlugin,
  MumaStorage: quietPlugin(),
  MumaSpeech: quietPlugin(),
  MumaDiagnostics: quietPlugin(),
  MumaSystem: quietPlugin(),
};

vi.mock("@capacitor/core", () => ({
  registerPlugin: (name) => plugins[name],
}));

window.Capacitor = { isNativePlatform: () => true };

const { default: Player } = await import("../../src/lib/Player.svelte");
const { currentTrack, isMobile, nowPlayingOpen, playerState, playlist, radioChannel, syncMode } =
  await import("../../src/lib/store.js");

const TRACKS = Array.from({ length: 6 }, (_, i) => ({
  id: `song-${i + 1}`,
  title: `Track ${i + 1}`,
  artist: "Angerfist",
  duration: 200,
}));

/** Lets bridge messages and the effects they trigger run for `ms` of real time. */
function settle(ms = BUFFERING_MS * 4) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * The layouts a tablet can show the next button in. `isMobile` is what `App.svelte` sets for a
 * coarse pointer at any width; Now Playing is where a tablet in landscape shows its controls.
 */
const LAYOUTS = [
  { name: "the desktop-style player bar", mobile: false, nowPlaying: false },
  { name: "the mini player of a touch screen (tablet)", mobile: true, nowPlaying: false },
  { name: "Now Playing on a touch screen (tablet)", mobile: true, nowPlaying: true },
];

async function renderOnFirst({ mobile, nowPlaying, playing }) {
  native.ids = TRACKS.map((track) => track.id);
  native.index = 0;
  native.playing = playing;
  playerState.set({ playing, repeat: "none", shuffle: false, volume: 50 });
  isMobile.set(mobile);
  nowPlayingOpen.set(nowPlaying);
  // The engine's cached snapshot is a module singleton; point it at the first track, as the
  // service's first report after boot does.
  fire("timeupdate", snapshot(settledStatus()));
  playlist.set(TRACKS);
  currentTrack.set(TRACKS[0]);
  render(Player, { onnavigate: vi.fn(), ontoggleQueue: vi.fn() });
  await settle();
  native.calls = [];
}

/** The next button the listener sees: Now Playing's when it is open, the bar's otherwise. */
function nextButton() {
  const buttons = screen.getAllByLabelText("Volgende");
  return buttons[buttons.length - 1];
}

describe("Player on the native shell: one tap on next (bug 108)", () => {
  beforeEach(() => {
    syncMode.set("off");
    radioChannel.set(null);
    global.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok" } }),
    }));
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  for (const layout of LAYOUTS) {
    describe(`from ${layout.name}`, () => {
      it("while playing: moves one track, keeps playing, and asks the service nothing else", async () => {
        await renderOnFirst({ ...layout, playing: true });

        await fireEvent.click(nextButton());
        await settle();

        expect(native.calls).toEqual(["next"]);
        expect(native.index).toBe(1);
        expect(get(currentTrack).id).toBe(TRACKS[1].id);
        expect(get(playerState).playing).toBe(true);
      });

      it("while paused: moves one track and stays paused", async () => {
        await renderOnFirst({ ...layout, playing: false });

        await fireEvent.click(nextButton());
        await settle();

        expect(native.calls).toEqual(["next"]);
        expect(native.index).toBe(1);
        expect(get(currentTrack).id).toBe(TRACKS[1].id);
        expect(get(playerState).playing).toBe(false);
      });

      it("two quick taps still move exactly two tracks and keep playing (bug 095)", async () => {
        await renderOnFirst({ ...layout, playing: true });

        await fireEvent.click(nextButton());
        await fireEvent.click(nextButton());
        await settle();

        expect(native.calls).toEqual(["next", "next"]);
        expect(native.index).toBe(2);
        expect(get(currentTrack).id).toBe(TRACKS[2].id);
        expect(get(playerState).playing).toBe(true);
      });
    });
  }
});
