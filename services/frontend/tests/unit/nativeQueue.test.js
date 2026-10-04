import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  createNativeQueue,
  isDifferentQueue,
  queueToPush,
  toQueueTrack,
  trackAfterCommand,
} from "../../src/lib/nativeQueue.js";

/**
 * The hand-off between the UI's queue and the platform service's.
 *
 * Each test here is one of the three rules in `nativeQueue.js`, and each of
 * them, broken, produces one of two symptoms on a phone: a track that restarts
 * from zero when it should not, or a queue edit that never arrives.
 */

/**
 * A player whose queue, current track and position the test can steer.
 *
 * It models the plugin as it behaves since !750, which is the half that
 * matters here: accepting a queue whose item at `index` is the item already
 * loaded rebuilds the list around it and does not address the player at all --
 * same track, same position, and `autoplay` ignored, because a queue edit is
 * not a transport command. Any other `index` loads that track from its start.
 * An earlier version of this fake restarted on every push, and a JS side
 * written against it shipped a payload that cost the listener 171 seconds.
 */
function fakePlayer(initial = {}) {
  const calls = [];
  let state = { trackId: null, position: 0, status: "idle", ...initial.state };
  let queue = { index: -1, length: 0, trackIds: [], ...initial.queue };
  return {
    ownsQueue: true,
    calls,
    state: () => state,
    /** Pretends the service is on a track, however far in. */
    nowPlaying(trackId, position = 0) {
      state = { ...state, trackId: trackId === null ? null : String(trackId), position };
    },
    async queueState() {
      calls.push(["queueState"]);
      return queue;
    },
    async setQueue(request) {
      calls.push(["setQueue", request]);
      const trackIds = request.tracks.map((t) => String(t.id));
      const wanted = trackIds[request.index] ?? null;
      queue = { index: request.index, length: trackIds.length, trackIds };
      if (wanted !== null && wanted === state.trackId) return queue;
      state = {
        ...state,
        trackId: wanted,
        position: 0,
        status: request.autoplay ? "playing" : state.status,
      };
      return queue;
    },
    async load(request) {
      calls.push(["load", request]);
      state = { ...state, trackId: String(request.trackId), position: 0 };
    },
  };
}

const TRACKS = [
  { id: 1, title: "One", artist: "A", album: "X", duration: 100, coverArt: "c1" },
  { id: 2, title: "Two", artist: "B", album: "X", duration: 200 },
  { id: 3, title: "Three", artist: "C", album: "Y", duration: 300 },
];

describe("toQueueTrack", () => {
  it("sends only what the notification and a head unit draw", () => {
    expect(toQueueTrack(TRACKS[0])).toEqual({
      id: "1",
      title: "One",
      artist: "A",
      album: "X",
      coverArt: "c1",
      duration: 100,
    });
  });

  it("never sends undefined across the bridge", () => {
    expect(toQueueTrack({ id: 9 })).toEqual({
      id: "9",
      title: "",
      artist: "",
      album: "",
      coverArt: "",
      duration: 0,
    });
  });

  // Bug report 150: a signed getCoverArt URL crossed the bridge as the cover,
  // and the service sent it back to the server as the id of a new request.
  it("sends the cover-art id, never a URL with the user's credentials", () => {
    const sent = toQueueTrack({ id: 7, coverArt: "art-824661-1786979739" });

    expect(sent.coverArt).toBe("art-824661-1786979739");
    expect(JSON.stringify(sent)).not.toMatch(/getCoverArt|[?&][tsu]=/);
  });
});

describe("isDifferentQueue", () => {
  it("treats never having pushed as different", () => {
    expect(isDifferentQueue(null, ["1"])).toBe(true);
  });

  it("is the same queue when the ids and their order match", () => {
    expect(isDifferentQueue(["1", "2"], ["1", "2"])).toBe(false);
    expect(isDifferentQueue(["1", "2"], ["2", "1"])).toBe(true);
    expect(isDifferentQueue(["1", "2"], ["1", "2", "3"])).toBe(true);
  });
});

describe("createNativeQueue", () => {
  let player;
  let queue;
  let onError;

  beforeEach(() => {
    player = fakePlayer();
    onError = vi.fn();
    queue = createNativeQueue(player, { onError });
  });

  it("pushes a new queue and starts it in the same call", async () => {
    await queue.sync(TRACKS, TRACKS[1]);

    expect(player.calls).toEqual([
      [
        "setQueue",
        {
          tracks: TRACKS.map((t) => toQueueTrack(t)),
          index: 1,
          autoplay: true,
        },
      ],
    ]);
  });

  // "Play that one instead", inside a list the service already holds. It is the
  // same call as every other change -- the plugin sees that the item at `index`
  // is not the one loaded and moves -- and never a `load` beside it: a `load`
  // that overtook its `setQueue` came back as "not in the queue".
  it("moves inside a queue it has already pushed with the index alone", async () => {
    await queue.sync(TRACKS, TRACKS[0]);
    player.calls.length = 0;

    await queue.sync([...TRACKS], TRACKS[1]);

    expect(player.calls).toEqual([
      ["setQueue", { tracks: TRACKS.map((t) => toQueueTrack(t)), index: 1, autoplay: true }],
    ]);
    expect(player.state().trackId).toBe("2");
  });

  // The third rule: a move the service made comes back into `currentTrack`, and
  // that write must not be sent straight back out again.
  it("asks for nothing when the service is already on that track", async () => {
    await queue.sync(TRACKS, TRACKS[0]);
    player.calls.length = 0;
    player.nowPlaying("3");

    await queue.sync(TRACKS, TRACKS[2]);

    expect(player.calls).toEqual([]);
  });

  it("can push a queue without starting it, which is what a boot does", async () => {
    await queue.sync(TRACKS, TRACKS[0], { autoplay: false });

    expect(player.calls).toEqual([
      [
        "setQueue",
        {
          tracks: TRACKS.map((t) => toQueueTrack(t)),
          index: 0,
          autoplay: false,
        },
      ],
    ]);
  });

  it("pushes an empty queue but asks for no track", async () => {
    await queue.sync([], null);

    expect(player.calls).toEqual([["setQueue", { tracks: [], index: 0, autoplay: false }]]);
  });

  // A card on the home screen, a search result: `currentTrack` moves and the
  // queue it came from does not exist. In a browser the engine simply plays
  // whatever the current track is; the service can only play what it holds, so
  // the track goes in front of the queue. In front of, and not instead of --
  // replacing it is what swallowed every later edit.
  it("puts a track played from outside the queue in front of it", async () => {
    const loose = { id: 99, title: "Loose", artist: "L", album: "Z", duration: 42 };

    await queue.sync(TRACKS, loose);

    expect(player.calls).toEqual([
      [
        "setQueue",
        {
          tracks: [loose, ...TRACKS].map((t) => toQueueTrack(t)),
          index: 0,
          autoplay: true,
        },
      ],
    ]);
    expect(queue.pushedIds()).toEqual(["99", "1", "2", "3"]);
  });

  // The same shape at boot means the opposite thing: the UI is following the
  // service rather than steering it, so the restored queue goes across and the
  // stray track starts nothing. Replacing a queue with one item because of a
  // leftover `currentTrack` is the one move phase 1 exists to prevent.
  it("pushes the restored queue, not the stray track, when a boot finds one", async () => {
    const loose = { id: 99, title: "Loose", artist: "L", album: "Z", duration: 42 };

    await queue.sync(TRACKS, loose, { autoplay: false });

    expect(player.calls).toEqual([
      [
        "setQueue",
        {
          tracks: TRACKS.map((t) => toQueueTrack(t)),
          index: 0,
          autoplay: false,
        },
      ],
    ]);
  });

  // A `load` that overtook the `setQueue` that put the track in the queue is
  // rejected by the plugin, so the order has to be guaranteed rather than likely.
  it("serialises every call onto one chain", async () => {
    const first = queue.sync(TRACKS, TRACKS[0]);
    const second = queue.sync([TRACKS[2]], TRACKS[2]);
    await Promise.all([first, second]);

    expect(player.calls.map(([name]) => name)).toEqual(["setQueue", "setQueue"]);
  });

  it("adopts the queue the service is already holding, and pushes nothing for it", async () => {
    player = fakePlayer({ queue: { index: 1, length: 3, trackIds: ["1", "2", "3"] } });
    player.nowPlaying("2");
    queue = createNativeQueue(player, { onError });

    await queue.adopt();
    expect(queue.pushedIds()).toEqual(["1", "2", "3"]);

    player.calls.length = 0;
    await queue.sync(TRACKS, TRACKS[1], { autoplay: false });

    expect(player.calls).toEqual([]);
  });

  // The native snapshot the service-already-there check reads (`player.state().trackId`) is not
  // trustworthy during an in-flight queue replacement: the plugin's own clear-and-reload sequence
  // walks it through `null`, an unrelated first item, and only then the one actually requested.
  // Two of those transient snapshots reaching the UI as `currentTrack` flips used to re-push a
  // `setQueue` the far side had already been told about, and the native reply to *that* push
  // produced the same transient sequence again -- a loop. Remembering the index of the last push
  // and comparing against that, rather than only the volatile native snapshot, is what stops it.
  it("does not re-push a queue and index it already pushed, even if the native snapshot lags", async () => {
    await queue.sync(TRACKS, TRACKS[1]);
    player.calls.length = 0;
    // A transient snapshot mid-replacement, as the plugin's own clear briefly produces.
    player.nowPlaying(null);

    await queue.sync(TRACKS, TRACKS[1]);

    expect(player.calls).toEqual([]);
  });

  // Increment F: `Player.svelte`'s `queueIndex` reads this to place the player's "next up"
  // and "add after current" against the native side's actual position.
  it("reports the adopted position through currentIndex", async () => {
    player = fakePlayer({ queue: { index: 2, length: 3, trackIds: ["1", "2", "3"] } });
    queue = createNativeQueue(player, { onError });

    expect(queue.currentIndex()).toBe(-1);
    await queue.adopt();

    expect(queue.currentIndex()).toBe(2);
  });

  it("reports the position of the last push through currentIndex", async () => {
    await queue.sync(TRACKS, TRACKS[2]);

    expect(queue.currentIndex()).toBe(2);
  });

  // The service moved by itself (a command, or its own plugin-driven advance) and the sync this
  // triggers asks for nothing because the far side is already there -- but `currentIndex()` still
  // has to catch up, or "next up" would keep previewing from the position of the last edit this
  // side made rather than from where playback actually is.
  it("catches currentIndex up to a move the service made by itself, even though nothing is pushed", async () => {
    await queue.sync(TRACKS, TRACKS[0]);
    player.nowPlaying("3");

    await queue.sync(TRACKS, TRACKS[2]);

    expect(player.calls).toHaveLength(1); // Only the first sync's setQueue.
    expect(queue.currentIndex()).toBe(2);
  });

  it("reports a failed hand-off instead of leaving a dead chain behind", async () => {
    player.setQueue = () => Promise.reject(new Error("no service"));

    await queue.sync(TRACKS, TRACKS[0]);
    expect(onError).toHaveBeenCalledTimes(1);

    player.setQueue = fakePlayer().setQueue;
    await queue.sync(TRACKS, TRACKS[0]);
    expect(onError).toHaveBeenCalledTimes(1);
  });
});

/**
 * Every way the UI can change the queue, as the service has to see it.
 *
 * The list the UI holds is the whole message: there is no "add" call and no
 * "move" call on the bridge, so each of these is one `setQueue` carrying the
 * complete queue and the position of the track that is playing. What every test
 * below also asserts is that the track playing did not move -- the defect these
 * cover reached the emulator as a set jumping back to its start, and then as an
 * added track that never played at all.
 */
describe("a queue mutation", () => {
  let player;
  let queue;

  /** The service playing `tracks`, on `current`, that many seconds in. */
  async function playing(tracks, current, position = 176) {
    player = fakePlayer();
    queue = createNativeQueue(player, { onError: () => {} });
    await queue.sync(tracks, current);
    player.nowPlaying(current.id, position);
    player.calls.length = 0;
  }

  /** The one payload that was pushed. */
  function pushed() {
    expect(player.calls).toHaveLength(1);
    const [name, request] = player.calls[0];
    expect(name).toBe("setQueue");
    return { ids: request.tracks.map((t) => t.id), index: request.index };
  }

  it("sends the added track along with the one that is playing", async () => {
    await playing([TRACKS[0]], TRACKS[0]);

    await queue.sync([TRACKS[0], TRACKS[1]], TRACKS[0]);

    expect(pushed()).toEqual({ ids: ["1", "2"], index: 0 });
    expect(player.state().trackId).toBe("1");
    expect(player.state().position).toBe(176);
  });

  // The defect as it was reported: nothing was in the queue store yet because
  // the track came off a card, so "add to queue" was pushed as the one track
  // that was already playing and the added one was simply not in the payload.
  it("reaches the service even while a track from outside the queue plays", async () => {
    const card = { id: 99, title: "Loose", artist: "L", album: "Z", duration: 42 };
    await playing([], card, 12);

    await queue.sync([TRACKS[1]], card);

    expect(pushed()).toEqual({ ids: ["99", "2"], index: 0 });
    expect(player.state().position).toBe(12);
  });

  it("puts a play-next straight after the track that is playing", async () => {
    await playing(TRACKS, TRACKS[1]);
    const fourth = { id: 4, title: "Four", artist: "D", album: "Y", duration: 400 };

    await queue.sync([TRACKS[0], TRACKS[1], fourth, TRACKS[2]], TRACKS[1]);

    expect(pushed()).toEqual({ ids: ["1", "2", "4", "3"], index: 1 });
    expect(player.state().position).toBe(176);
  });

  it("sends a removal as the queue that is left", async () => {
    await playing(TRACKS, TRACKS[1]);

    await queue.sync([TRACKS[1], TRACKS[2]], TRACKS[1]);

    expect(pushed()).toEqual({ ids: ["2", "3"], index: 0 });
    expect(player.state().position).toBe(176);
  });

  it("sends a reorder as the new order, with the current track where it landed", async () => {
    await playing(TRACKS, TRACKS[2]);

    await queue.sync([TRACKS[2], TRACKS[0], TRACKS[1]], TRACKS[2]);

    expect(pushed()).toEqual({ ids: ["3", "1", "2"], index: 0 });
    expect(player.state().position).toBe(176);
  });

  // Clearing the queue does not stop the music: the UI empties `playlist` and
  // leaves `currentTrack` alone, which is a queue of one and exactly what a
  // browser does with the same stores.
  it("leaves the track that is playing when the queue is cleared", async () => {
    await playing(TRACKS, TRACKS[1]);

    await queue.sync([], TRACKS[1]);

    expect(pushed()).toEqual({ ids: ["2"], index: 0 });
    expect(player.state().position).toBe(176);
  });

  it("plays this list from this index when a track in it is tapped", async () => {
    await playing([], TRACKS[0], 30);

    await queue.sync(TRACKS, TRACKS[2]);

    expect(pushed()).toEqual({ ids: ["1", "2", "3"], index: 2 });
    expect(player.state().trackId).toBe("3");
    expect(player.state().position).toBe(0);
  });
});

describe("queueToPush", () => {
  it("is the UI's queue when the current track is in it", () => {
    expect(queueToPush(TRACKS, TRACKS[1])).toEqual({ queue: TRACKS, index: 1 });
  });

  it("points at nothing when there is no current track", () => {
    expect(queueToPush(TRACKS, null)).toEqual({ queue: TRACKS, index: -1 });
  });

  it("ignores a current track outside the queue at boot, where the UI follows", () => {
    expect(queueToPush(TRACKS, { id: 99 }, true)).toEqual({ queue: TRACKS, index: -1 });
  });
});

/**
 * The mirror: the service advanced by itself and the UI has to end up on the
 * track it is actually playing.
 */
describe("trackAfterCommand", () => {
  it("follows the track the snapshot names", () => {
    expect(trackAfterCommand(TRACKS, "1", { name: "next", trackId: "2" })).toBe(TRACKS[1]);
  });

  // The plugin notifies the new state and the move as two bridge messages, so a
  // `next` can arrive while the snapshot still names the track it left. Sitting
  // still there is what made the UI lag a track behind the notification.
  it("steps the queue when the snapshot has not caught up with the move", () => {
    expect(trackAfterCommand(TRACKS, "1", { name: "next", trackId: "1" })).toBe(TRACKS[1]);
    expect(trackAfterCommand(TRACKS, "2", { name: "previous", trackId: "2" })).toBe(TRACKS[0]);
  });

  it("guesses at no wrap past either end of the queue", () => {
    expect(trackAfterCommand(TRACKS, "3", { name: "next", trackId: "3" })).toBeNull();
    expect(trackAfterCommand(TRACKS, "1", { name: "previous", trackId: "1" })).toBeNull();
  });

  it("moves nothing for a command that is not a move", () => {
    expect(trackAfterCommand(TRACKS, "1", { name: "play", trackId: "1" })).toBeNull();
    expect(trackAfterCommand(TRACKS, "1", { name: "seekTo", trackId: "1" })).toBeNull();
  });

  it("stays put when the service is on a track the UI's queue does not hold", () => {
    expect(trackAfterCommand(TRACKS, "1", { name: "next", trackId: "99" })).toBeNull();
  });

  it("survives a command with nothing in it", () => {
    expect(trackAfterCommand(TRACKS, "1", {})).toBeNull();
    expect(trackAfterCommand(TRACKS, null, { name: "next" })).toBeNull();
  });

  // A self-inflicted queue replacement clears the native timeline before loading the new list,
  // and the transient snapshot that produces along the way -- no track, nothing queued -- is not
  // a lagging move to step past: it is the plugin talking to itself. Stepping on it is what turned
  // one `setQueue` into a `previous` immediately followed by a `next`, which the UI mirrored back
  // into another `setQueue`, forever. See TransportTracker.kt for the Kotlin half of this fix.
  it("treats an empty snapshot as no move, not a lagging one", () => {
    expect(
      trackAfterCommand(TRACKS, "2", { name: "previous", trackId: null, queueLength: 0 }),
    ).toBeNull();
    expect(
      trackAfterCommand(TRACKS, "2", { name: "next", trackId: null, queueLength: 0 }),
    ).toBeNull();
  });

  // The bail-out above is specifically for `queueLength: 0`. A caller that does not know the
  // native queue length at all (an older event shape, or a test) gets the pre-existing step
  // behaviour rather than being silently treated as empty.
  it("still steps by name when queueLength was not reported at all", () => {
    expect(trackAfterCommand(TRACKS, "1", { name: "next", trackId: null })).toBe(TRACKS[1]);
  });
});

// Bug report 095: a mirror of a service report that was replayed as a request, and a service
// report from before the newest requested move that was applied as current.
describe("createNativeQueue: mirrors and stale reports", () => {
  const LIST = [{ id: "1" }, { id: "2" }, { id: "3" }];

  it("never sends a followed track back, even when the engine has moved on by then", async () => {
    const player = fakePlayer({
      state: { trackId: "1" },
      queue: { index: 0, length: 3, trackIds: ["1", "2", "3"] },
    });
    const queue = createNativeQueue(player);
    await queue.adopt();

    queue.follow("2");
    // By the time the chain runs, the snapshot already names the track after it.
    player.nowPlaying("3");
    await queue.sync(LIST, LIST[1]);

    expect(player.calls.filter(([name]) => name === "setQueue")).toEqual([]);
    expect(queue.currentIndex()).toBe(1);
  });

  it("treats a report of another track as stale while a requested move is in flight", async () => {
    const player = fakePlayer({
      state: { trackId: "1" },
      queue: { index: 0, length: 3, trackIds: ["1", "2", "3"] },
    });
    const queue = createNativeQueue(player);
    await queue.adopt();

    const first = queue.sync(LIST, LIST[1]);
    const second = queue.sync(LIST, LIST[2]);

    expect(queue.isStale("2")).toBe(true);
    expect(queue.isStale("3")).toBe(false);
    await first;
    await second;
    // Every requested move has finished: whatever the service says now is the truth.
    expect(queue.isStale("2")).toBe(false);
  });

  it("does not hold back reports for a queue edit that keeps the current track", async () => {
    const player = fakePlayer({
      state: { trackId: "1" },
      queue: { index: 0, length: 3, trackIds: ["1", "2", "3"] },
    });
    const queue = createNativeQueue(player);
    await queue.adopt();
    await queue.sync(LIST, LIST[0], { autoplay: false });

    const edit = queue.sync([...LIST, { id: "4" }], LIST[0]);

    // The service advancing on its own during the edit's round trip must still reach the UI.
    expect(queue.isStale("2")).toBe(false);
    await edit;
  });
});
