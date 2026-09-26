import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import { get } from "svelte/store";

/**
 * Bug report 095: two quick taps on "next" on the phone left the player flickering between the
 * current and the next track forever.
 *
 * The fake below is a small simulation of the `MumaPlayer` plugin rather than a recorder, because
 * the defect only exists in the ordering between the two sides: the plugin answers a `setQueue`
 * with the settled `durationchange` first and the call's resolution after it, as two separate
 * bridge messages, and a `next` reports the move it made (`durationchange` plus `command: next`)
 * with the state as it was at the moment of the call -- Media3's controller masks every call, so
 * two quick `seekToNext` calls land on +1 and then +2.
 *
 * Its own file for the same reason as `playerNativeMode.test.js`: `Player.svelte` reads
 * `platform.player.ownsQueue` once, at import time.
 */

/** Stops a feedback loop from running the test forever; a settled player never gets near it. */
const LOOP_GUARD = 40;

const native = { ids: [], index: -1, setQueueCalls: 0 };

const handlers = new Map();

/** Delivers `fn` the way a bridge message arrives: as its own macrotask. */
function bridge(fn) {
  setTimeout(fn, 0);
}

function snapshot() {
  return {
    status: "playing",
    position: 0,
    duration: 200,
    trackId: native.ids[native.index] ?? null,
    queueIndex: native.index,
    queueLength: native.ids.length,
  };
}

function fire(event, payload) {
  handlers.get(event)?.(payload);
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
    state: vi.fn(async () => snapshot()),
    setQueue: vi.fn(
      (request) =>
        new Promise((resolve) => {
          native.setQueueCalls += 1;
          const answer = () => ({
            index: native.index,
            length: native.ids.length,
            trackIds: native.ids.slice(),
          });
          if (native.setQueueCalls > LOOP_GUARD) {
            resolve(answer());
            return;
          }
          bridge(() => {
            const wanted = request.tracks[request.index]?.id ?? null;
            const moved = wanted !== (native.ids[native.index] ?? null);
            native.ids = request.tracks.map((track) => String(track.id));
            native.index = request.index;
            // TransportTracker swallows every intermediate state of a replacement and settles
            // quietly on the requested item: a durationchange, never a command. Keeping the current
            // item (QueuePlan.KeepCurrent) reports nothing at all.
            if (moved) fire("durationchange", snapshot());
            bridge(() => resolve(answer()));
          });
        }),
    ),
    next: vi.fn(async () => {
      if (native.index + 1 >= native.ids.length) return {};
      native.index += 1;
      const state = snapshot();
      bridge(() => {
        fire("durationchange", state);
        fire("command", { name: "next" });
      });
      return {};
    }),
    previous: vi.fn(async () => {
      if (native.index <= 0) return {};
      native.index -= 1;
      const state = snapshot();
      bridge(() => {
        fire("durationchange", state);
        fire("command", { name: "previous" });
      });
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
function settle(ms = 60) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function renderOnFirst() {
  native.ids = TRACKS.map((track) => track.id);
  native.index = 0;
  native.setQueueCalls = 0;
  // The engine's cached snapshot is a module singleton; point it at the first track, as the
  // service's first report after boot does.
  fire("timeupdate", snapshot());
  playlist.set(TRACKS);
  currentTrack.set(TRACKS[0]);
  render(Player, { onnavigate: vi.fn(), ontoggleQueue: vi.fn() });
  await settle();
  playerPlugin.setQueue.mockClear();
  playerPlugin.next.mockClear();
  playerPlugin.previous.mockClear();
  native.setQueueCalls = 0;
}

describe("Player on the native shell: rapid transport taps (bug 095)", () => {
  beforeEach(() => {
    playerState.set({ playing: true, repeat: "none", shuffle: false, volume: 50 });
    syncMode.set("off");
    radioChannel.set(null);
    isMobile.set(false);
    nowPlayingOpen.set(false);
    global.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok" } }),
    }));
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("two quick taps on next advance exactly two tracks and settle", async () => {
    await renderOnFirst();
    const button = screen.getByLabelText("Volgende");

    // The second tap lands before the service has reported the first move.
    await fireEvent.click(button);
    await fireEvent.click(button);
    await settle();
    const callsAfterSettling = native.setQueueCalls;
    await settle();

    expect(native.index).toBe(2);
    expect(get(currentTrack).id).toBe(TRACKS[2].id);
    // Settled: nothing is still bouncing between the two sides.
    expect(native.setQueueCalls).toBe(callsAfterSettling);
    // "next" is an intent for the service, not an index computed here and pushed as a new queue.
    expect(playerPlugin.next).toHaveBeenCalledTimes(2);
    expect(playerPlugin.setQueue).not.toHaveBeenCalled();
  });

  it("N quick taps advance N tracks", async () => {
    await renderOnFirst();
    const button = screen.getByLabelText("Volgende");

    for (let tap = 0; tap < 4; tap += 1) await fireEvent.click(button);
    await settle(100);

    expect(native.index).toBe(4);
    expect(get(currentTrack).id).toBe(TRACKS[4].id);
    expect(playerPlugin.setQueue).not.toHaveBeenCalled();
  });

  it("quick taps on previous go back through the service as well", async () => {
    await renderOnFirst();
    // renderOnFirst puts the service on the first track; walk it forward to the fourth first.
    native.index = 3;
    fire("durationchange", snapshot());
    await settle();

    const button = screen.getByLabelText("Vorige");
    await fireEvent.click(button);
    await fireEvent.click(button);
    await settle();

    expect(native.index).toBe(1);
    expect(get(currentTrack).id).toBe(TRACKS[1].id);
    expect(playerPlugin.previous).toHaveBeenCalledTimes(2);
    expect(playerPlugin.setQueue).not.toHaveBeenCalled();
  });

  // The same race without the next button: two tracks picked from the list in quick succession
  // each push a queue with a new index. The first push's settled report arrives after the second
  // pick, and mirroring it re-imposed the first pick -- whose push then undid the second, and so on.
  it("two quick picks from the list settle on the last one", async () => {
    await renderOnFirst();

    currentTrack.set(TRACKS[3]);
    await Promise.resolve();
    await Promise.resolve();
    currentTrack.set(TRACKS[4]);
    await settle();
    const callsAfterSettling = native.setQueueCalls;
    await settle();

    expect(native.index).toBe(4);
    expect(get(currentTrack).id).toBe(TRACKS[4].id);
    expect(native.setQueueCalls).toBe(callsAfterSettling);
    expect(native.setQueueCalls).toBe(2);
  });

  // The notification, a headset and a head unit move the service themselves and the UI follows.
  // Two presses in quick succession must be followed, not answered with a queue of their own.
  it("follows two quick moves made outside the app without pushing anything back", async () => {
    await renderOnFirst();

    await playerPlugin.next();
    await playerPlugin.next();
    await settle();

    expect(get(currentTrack).id).toBe(TRACKS[2].id);
    expect(playerPlugin.setQueue).not.toHaveBeenCalled();
  });
});
