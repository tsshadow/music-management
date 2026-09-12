import { describe, it, expect, beforeEach, vi } from "vitest";
import { createNativeQueue, isDifferentQueue, toQueueTrack } from "../../src/lib/nativeQueue.js";

/**
 * The hand-off between the UI's queue and the platform service's.
 *
 * Each test here is one of the three rules in `nativeQueue.js`, and each of
 * them, broken, produces the same symptom on a phone: a track that restarts
 * from zero when it should not.
 */

/** A player whose queue and current track the test can steer. */
function fakePlayer(initial = {}) {
  const calls = [];
  let state = { trackId: null, ...initial.state };
  let queue = { index: -1, length: 0, trackIds: [], ...initial.queue };
  return {
    ownsQueue: true,
    calls,
    state: () => state,
    /** Pretends the service moved on, which is what a `command` event follows. */
    nowPlaying(trackId) {
      state = { ...state, trackId };
    },
    async queueState() {
      calls.push(["queueState"]);
      return queue;
    },
    async setQueue(request) {
      calls.push(["setQueue", request]);
      queue = {
        index: request.index,
        length: request.tracks.length,
        trackIds: request.tracks.map((t) => String(t.id)),
      };
      // What the plugin does, and the reason this fake once hid a bug that
      // stopped every tapped track from playing: accepting a queue also
      // positions the service on `index`, so the next call sees that track
      // already loaded.
      state = { ...state, trackId: queue.trackIds[request.index] ?? null };
      return queue;
    },
    async load(request) {
      calls.push(["load", request]);
      state = { ...state, trackId: String(request.trackId) };
    },
  };
}

const TRACKS = [
  { id: 1, title: "One", artist: "A", album: "X", duration: 100, coverArt: "c1" },
  { id: 2, title: "Two", artist: "B", album: "X", duration: 200 },
  { id: 3, title: "Three", artist: "C", album: "Y", duration: 300 },
];

const artworkUrlFor = (track) => (track.coverArt ? `/art/${track.coverArt}` : "");

describe("toQueueTrack", () => {
  it("sends only what the notification and a head unit draw", () => {
    expect(toQueueTrack(TRACKS[0], artworkUrlFor)).toEqual({
      id: "1",
      title: "One",
      artist: "A",
      album: "X",
      artworkUrl: "/art/c1",
      duration: 100,
    });
  });

  it("never sends undefined across the bridge", () => {
    expect(toQueueTrack({ id: 9 }, () => undefined)).toEqual({
      id: "9",
      title: "",
      artist: "",
      album: "",
      artworkUrl: "",
      duration: 0,
    });
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
    queue = createNativeQueue(player, { artworkUrlFor, onError });
  });

  it("pushes a new queue and starts it in the same call", async () => {
    await queue.sync(TRACKS, TRACKS[1]);

    expect(player.calls).toEqual([
      [
        "setQueue",
        {
          tracks: TRACKS.map((t) => toQueueTrack(t, artworkUrlFor)),
          index: 1,
          autoplay: true,
        },
      ],
    ]);
  });

  // The second rule: re-pushing an identical list makes the service seek to the
  // start of the item, which is how a restored position disappears.
  it("does not push the same queue twice", async () => {
    await queue.sync(TRACKS, TRACKS[0]);
    player.calls.length = 0;

    await queue.sync([...TRACKS], TRACKS[1]);

    expect(player.calls).toEqual([["load", { trackId: "2", autoplay: true }]]);
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
          tracks: TRACKS.map((t) => toQueueTrack(t, artworkUrlFor)),
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
  // whatever the current track is; the service can only play what it holds.
  it("makes a track the queue when the UI plays one outside it", async () => {
    const loose = { id: 99, title: "Loose", artist: "L", album: "Z", duration: 42 };

    await queue.sync(TRACKS, loose);

    expect(player.calls).toEqual([
      ["setQueue", { tracks: [toQueueTrack(loose, artworkUrlFor)], index: 0, autoplay: true }],
    ]);
    expect(queue.pushedIds()).toEqual(["99"]);
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
          tracks: TRACKS.map((t) => toQueueTrack(t, artworkUrlFor)),
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
    queue = createNativeQueue(player, { artworkUrlFor, onError });

    await queue.adopt();
    expect(queue.pushedIds()).toEqual(["1", "2", "3"]);

    player.calls.length = 0;
    await queue.sync(TRACKS, TRACKS[1], { autoplay: false });

    expect(player.calls).toEqual([]);
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
