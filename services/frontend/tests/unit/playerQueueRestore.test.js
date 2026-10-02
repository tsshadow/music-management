import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/svelte";
import { get } from "svelte/store";

/**
 * Issue #113: the app mounts before the queue restore has finished, so `Player.svelte` is up --
 * with its queue sync to the player service -- while the restore is still looking tracks up.
 *
 * Pins the constraint the issue set: nothing that mounts early pushes an empty or partial queue
 * to the service while the restore runs. A restore that finishes is adopted without a push or
 * autoplay; a track the listener starts first cancels it and is what plays.
 *
 * Its own file for the same reason as `playerNativeMode.test.js`: `Player.svelte` reads
 * `platform.player.ownsQueue` once, at import time.
 */

const native = { ids: [], index: -1 };
const handlers = new Map();

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
    setQueue: vi.fn(async ({ tracks, index }) => {
      native.ids = tracks.map((track) => track.id);
      native.index = index;
      return { index, length: native.ids.length, trackIds: native.ids.slice() };
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
const { startQueue } = await import("../../src/lib/queue.js");
const { beginQueueRestore, cancelQueueRestore, queueRestore } =
  await import("../../src/lib/queueRestore.js");
const { LAZY_HOOK_TIMEOUT_MS, loadLazy } = await import("./lazyTestUtils.js");
beforeAll(() => loadLazy("nowPlaying"), LAZY_HOOK_TIMEOUT_MS);

const TRACKS = Array.from({ length: 3 }, (_, i) => ({
  id: `song-${i + 1}`,
  title: `Track ${i + 1}`,
  artist: "Angerfist",
  duration: 200,
}));
const STALE = [{ id: "stale-1", title: "Yesterday's queue", artist: "Someone", duration: 100 }];
const CHOSEN = {
  id: "chosen",
  title: "Picked during the restore",
  artist: "Miss K8",
  duration: 180,
};

/** Lets bridge calls and the effects they trigger run. */
function settle(ms = 40) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * The state the app mounts in on a start with a queue on the service: the service on track 2 of
 * three, yesterday's queue still in localStorage, and the restore just begun.
 */
async function mountDuringRestore({ mobile = true } = {}) {
  native.ids = TRACKS.map((track) => track.id);
  native.index = 1;
  handlers.get("timeupdate")?.({
    status: "playing",
    position: 10,
    duration: 200,
    trackId: native.ids[1],
    queueIndex: 1,
    queueLength: 3,
  });
  playlist.set(STALE);
  currentTrack.set(STALE[0]);
  const ticket = beginQueueRestore();
  isMobile.set(mobile);
  render(Player, { onnavigate: vi.fn(), ontoggleQueue: vi.fn() });
  await settle();
  return ticket;
}

describe("Player while the app-start queue restore runs (issue #113)", () => {
  beforeEach(() => {
    cancelQueueRestore();
    queueRestore.set({ status: "idle", done: 0, total: 0 });
    syncMode.set("off");
    radioChannel.set(null);
    nowPlayingOpen.set(false);
    playerState.set({ playing: true, repeat: "none", shuffle: false, volume: 50 });
    global.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok" } }),
    }));
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("pushes nothing to the service -- neither yesterday's queue nor an empty one", async () => {
    await mountDuringRestore();

    expect(playerPlugin.setQueue).not.toHaveBeenCalled();
    expect(native.ids).toEqual(TRACKS.map((track) => track.id));
  });

  it("shows the restoring state with a spinner in the mini player", async () => {
    await mountDuringRestore();

    const row = screen.getByTestId("queue-restoring");
    expect(row.textContent).toContain("Wachtrij wordt hersteld…");
    expect(row.querySelector('[data-testid="throbber"]')).not.toBeNull();
    expect(screen.queryByText("Niets aan het afspelen")).toBeNull();
  });

  it("shows the restoring state in the wide player bar too", async () => {
    await mountDuringRestore({ mobile: false });

    expect(screen.getByTestId("queue-restoring")).toBeTruthy();
  });

  it("pushes nothing while a queue edit lands mid-restore", async () => {
    await mountDuringRestore();

    playlist.update((tracks) => [...tracks, CHOSEN]);
    await settle();

    expect(get(queueRestore).status).toBe("restoring");
    expect(playerPlugin.setQueue).not.toHaveBeenCalled();
  });

  it("adopts a finished restore without a push and shows the playing track", async () => {
    const ticket = await mountDuringRestore();

    ticket.write(() => {
      startQueue(TRACKS, { view: null });
      currentTrack.set(TRACKS[1]);
    });
    ticket.finish();
    await settle();

    expect(playerPlugin.setQueue).not.toHaveBeenCalled();
    expect(screen.queryByTestId("queue-restoring")).toBeNull();
    expect(screen.getByText("Track 2")).toBeTruthy();
  });

  it("never autoplays a restored queue that differs from the service's", async () => {
    const ticket = await mountDuringRestore();

    // Track 3 no longer resolves on the server, so the restored list is shorter.
    ticket.write(() => {
      startQueue(TRACKS.slice(0, 2), { view: null });
      currentTrack.set(TRACKS[1]);
    });
    ticket.finish();
    await settle();

    expect(playerPlugin.setQueue).toHaveBeenCalled();
    for (const [request] of playerPlugin.setQueue.mock.calls) {
      expect(request.autoplay).toBe(false);
    }
  });

  it("plays a track the listener starts during the restore, and the late restore changes nothing", async () => {
    const ticket = await mountDuringRestore();

    startQueue([CHOSEN], { view: "home" });
    currentTrack.set(CHOSEN);
    await settle();

    expect(get(queueRestore).status).toBe("cancelled");
    expect(playerPlugin.setQueue).toHaveBeenCalledTimes(1);
    const [request] = playerPlugin.setQueue.mock.calls[0];
    expect(request.tracks.map((track) => track.id)).toEqual(["chosen"]);
    expect(request.autoplay).toBe(true);

    const written = ticket.write(() => {
      startQueue(TRACKS, { view: null });
      currentTrack.set(TRACKS[1]);
    });
    ticket.finish();
    await settle();

    expect(written).toBe(false);
    expect(get(currentTrack)).toEqual(CHOSEN);
    expect(playerPlugin.setQueue).toHaveBeenCalledTimes(1);
  });
});
