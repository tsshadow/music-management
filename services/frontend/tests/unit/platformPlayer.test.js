import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { get } from "svelte/store";
import { createBrowserPlayer } from "../../src/lib/platform/browser/player.js";
import { audio } from "../../src/lib/store.js";
import * as equalizer from "../../src/lib/equalizer.js";
import { EQ_PRESETS } from "../../src/lib/equalizerPresets.js";

/**
 * An element the way jsdom leaves it, with the two methods it does not
 * implement stubbed the way the Player tests stub them.
 */
function makeElement() {
  const element = document.createElement("audio");
  element.play = vi.fn(async () => {
    Object.defineProperty(element, "paused", { value: false, configurable: true });
  });
  element.pause = vi.fn(() => {
    Object.defineProperty(element, "paused", { value: true, configurable: true });
  });
  Object.defineProperty(element, "paused", { value: true, configurable: true });
  return element;
}

/** Overrides one of the read-only properties jsdom will not let a test set. */
function pretend(element, property, value) {
  Object.defineProperty(element, property, { value, configurable: true, writable: true });
}

describe("browser player", () => {
  let player;
  let element;

  beforeEach(() => {
    player = createBrowserPlayer();
    element = makeElement();
  });

  afterEach(() => {
    player.detach();
    vi.restoreAllMocks();
  });

  describe("the element it drives", () => {
    it("has nothing to drive until one is attached", () => {
      expect(player.ready()).toBe(false);
      expect(player.element()).toBeNull();
      expect(player.state()).toEqual({
        status: "idle",
        position: 0,
        duration: 0,
        trackId: null,
        volume: 1,
        buffering: false,
      });
    });

    // Other modules read the element from this store; it is the engine that
    // owns it, so it is the engine that publishes it.
    it("publishes the element it was given", () => {
      player.attach(element);

      expect(player.ready()).toBe(true);
      expect(player.element()).toBe(element);
      expect(get(audio)).toBe(element);
    });

    it("lets go of it again", () => {
      player.attach(element);
      player.detach();

      expect(player.ready()).toBe(false);
      expect(get(audio)).toBeNull();
    });

    // A second Player mounting -- which is what every render in a test suite
    // does -- must not leave the first one's listeners behind, or every event
    // would be handled twice.
    it("drops the listeners of the element it leaves behind", () => {
      const handler = vi.fn();
      player.attach(element);
      player.on("timeupdate", handler);
      player.attach(makeElement());

      element.dispatchEvent(new Event("timeupdate"));

      expect(handler).not.toHaveBeenCalled();
    });

    it("attaching the same element twice changes nothing", () => {
      player.attach(element);
      player.load({ url: "/rest/stream?id=song-1", trackId: "song-1" });
      player.attach(element);

      expect(player.state().trackId).toBe("song-1");
    });
  });

  describe("the transport", () => {
    beforeEach(() => {
      player.attach(element);
    });

    it("loads a source and remembers what it is playing", async () => {
      await player.load({ url: "/rest/stream?id=song-1", trackId: "song-1" });

      expect(element.src).toContain("/rest/stream?id=song-1");
      expect(player.state().trackId).toBe("song-1");
      expect(element.play).not.toHaveBeenCalled();
    });

    it("starts at a position when asked to", async () => {
      await player.load({ url: "/rest/stream?id=song-1", position: 42 });

      expect(element.currentTime).toBe(42);
    });

    it("plays straight away when asked to", async () => {
      await player.load({ url: "/rest/stream?id=song-1", autoplay: true });

      expect(element.play).toHaveBeenCalled();
      expect(player.state().status).toBe("playing");
    });

    // The caller decides what a refused play means -- skipping a track cancels
    // the previous one's play(), which is an AbortError and not a failure.
    it("hands a refused play back to the caller", async () => {
      element.play = vi.fn(async () => {
        throw new Error("NotAllowedError");
      });

      await expect(player.load({ url: "/rest/stream?id=1", autoplay: true })).rejects.toThrow(
        "NotAllowedError",
      );
    });

    it("has nothing to load without a url", async () => {
      await player.load({ url: "" });

      expect(player.state().status).toBe("idle");
    });

    it("plays, pauses and seeks", async () => {
      await player.load({ url: "/rest/stream?id=song-1" });

      await player.play();
      expect(player.state().status).toBe("playing");

      pretend(element, "readyState", 4);
      player.pause();
      expect(player.state().status).toBe("paused");

      player.seek(30);
      expect(player.state().position).toBe(30);
    });

    it("stopping lets go of the source", async () => {
      await player.load({ url: "/rest/stream?id=song-1", trackId: "song-1" });

      player.stop();

      expect(element.pause).toHaveBeenCalled();
      expect(element.hasAttribute("src")).toBe(false);
      expect(player.state()).toMatchObject({ status: "idle", trackId: null });
    });

    it("keeps the volume between silence and full", () => {
      player.setVolume(0.25);
      expect(player.state().volume).toBeCloseTo(0.25);

      player.setVolume(2);
      expect(player.state().volume).toBe(1);

      player.setVolume(-1);
      expect(player.state().volume).toBe(0);
    });

    it("changes the playback rate, which is how the radio stays in step", () => {
      player.setRate(1.02);

      expect(element.playbackRate).toBeCloseTo(1.02);
    });

    it("a transport command without an element is not an error", () => {
      player.detach();

      expect(() => {
        player.pause();
        player.stop();
        player.seek(10);
        player.setVolume(0.5);
        player.setRate(1);
      }).not.toThrow();
    });

    it("playing without an element resolves instead of throwing", async () => {
      player.detach();

      await expect(player.play()).resolves.toBeUndefined();
    });

    // Shuffle and repeat stay `Player.svelte`'s own decision here -- there is no
    // service on this side of the bridge for either to live on -- so the engine
    // has nothing to do beyond answering, the same as `setQueue`/`queueState`.
    it("has nowhere to put a mode, and says so by doing nothing", async () => {
      await expect(player.setMode({ shuffle: true, repeat: "all" })).resolves.toEqual(
        player.state(),
      );
    });
  });

  describe("the state it reports", () => {
    beforeEach(async () => {
      player.attach(element);
      await player.load({ url: "/rest/stream?id=song-1", trackId: "song-1" });
    });

    it("reports the length the element measured", () => {
      pretend(element, "duration", 240);

      expect(player.state().duration).toBe(240);
    });

    // A transcoded stream arrives chunked and without a Content-Length, which
    // leaves duration at Infinity. Callers fall back to the library's length,
    // so the engine has to say it has none rather than pass Infinity on.
    it("reports no length for a stream that has none of its own", () => {
      pretend(element, "duration", Infinity);
      expect(player.state().duration).toBe(0);

      pretend(element, "duration", NaN);
      expect(player.state().duration).toBe(0);
    });

    it("is loading while nothing has arrived yet", () => {
      expect(player.state().status).toBe("loading");
    });

    it("is playing exactly when the element is not paused", async () => {
      await player.play();

      expect(player.state().status).toBe("playing");
    });

    it("is ended when the element ran out", () => {
      pretend(element, "ended", true);
      pretend(element, "readyState", 4);

      expect(player.state().status).toBe("ended");
    });

    it("is paused once there is something to play", () => {
      pretend(element, "readyState", 4);

      expect(player.state().status).toBe("paused");
    });

    it("is in error after the source failed, and loads out of it", async () => {
      element.dispatchEvent(new Event("error"));
      expect(player.state().status).toBe("error");

      await player.load({ url: "/rest/stream?id=song-2", trackId: "song-2" });

      expect(player.state().status).toBe("loading");
    });
  });

  describe("the events it emits", () => {
    beforeEach(() => {
      player.attach(element);
    });

    it("passes the element's events on with a snapshot", () => {
      const handlers = {
        timeupdate: vi.fn(),
        durationchange: vi.fn(),
        play: vi.fn(),
        pause: vi.fn(),
        ended: vi.fn(),
        error: vi.fn(),
        volumechange: vi.fn(),
      };
      for (const [event, handler] of Object.entries(handlers)) player.on(event, handler);
      pretend(element, "currentTime", 12);

      element.dispatchEvent(new Event("timeupdate"));
      // The length is known on loadedmetadata; that is what durationchange means
      // here, and what a native engine reports when its timeline settles.
      element.dispatchEvent(new Event("loadedmetadata"));
      element.dispatchEvent(new Event("play"));
      element.dispatchEvent(new Event("pause"));
      element.dispatchEvent(new Event("ended"));
      element.dispatchEvent(new Event("error"));
      element.dispatchEvent(new Event("volumechange"));

      for (const handler of Object.values(handlers)) expect(handler).toHaveBeenCalledTimes(1);
      expect(handlers.timeupdate.mock.calls[0][0]).toMatchObject({ position: 12 });
    });

    it("stops calling a handler that unsubscribed", () => {
      const handler = vi.fn();
      const unsubscribe = player.on("timeupdate", handler);

      unsubscribe();
      element.dispatchEvent(new Event("timeupdate"));

      expect(handler).not.toHaveBeenCalled();
    });

    it("refuses an event nobody emits, rather than never calling the handler", () => {
      expect(() => player.on("loadedmetadata", vi.fn())).toThrow(/Unknown player event/);
    });

    // The LG TV browser fires timeupdate only on a state change and never on the
    // cadence the spec asks for, so the engine polls while it plays.
    it("follows the position on a timer while it plays", async () => {
      vi.useFakeTimers();
      try {
        const handler = vi.fn();
        player.on("timeupdate", handler);
        await player.load({ url: "/rest/stream?id=song-1", autoplay: true });

        // No `timeupdate` is dispatched at any point.
        element.dispatchEvent(new Event("play"));
        await vi.advanceTimersByTimeAsync(300);

        expect(handler).toHaveBeenCalled();
      } finally {
        vi.useRealTimers();
      }
    });

    it("stops polling once it is paused", async () => {
      vi.useFakeTimers();
      try {
        const handler = vi.fn();
        player.on("timeupdate", handler);
        await player.load({ url: "/rest/stream?id=song-1", autoplay: true });

        element.dispatchEvent(new Event("play"));
        await vi.advanceTimersByTimeAsync(300);
        const ticks = handler.mock.calls.length;
        player.pause();
        element.dispatchEvent(new Event("pause"));
        await vi.advanceTimersByTimeAsync(1000);

        expect(handler.mock.calls.length).toBe(ticks);
      } finally {
        vi.useRealTimers();
      }
    });
  });

  // The play button shows a throbber while this flag is up. `status` stays
  // `playing` meanwhile: the element is not paused, and a press must pause it.
  describe("buffering", () => {
    let handler;

    beforeEach(async () => {
      player.attach(element);
      handler = vi.fn();
      player.on("buffering", handler);
      await player.load({ url: "/rest/stream?id=song-1", trackId: "song-1", autoplay: true });
      element.dispatchEvent(new Event("play"));
    });

    it("is not buffering before the element waits for data", () => {
      expect(player.state().buffering).toBe(false);
      expect(handler).not.toHaveBeenCalled();
    });

    it("is buffering while a play request waits for data, and still playing", () => {
      element.dispatchEvent(new Event("waiting"));

      expect(player.state()).toMatchObject({ buffering: true, status: "playing" });
      expect(handler).toHaveBeenCalledTimes(1);
      expect(handler.mock.calls[0][0]).toMatchObject({ buffering: true });
    });

    it("emits once per change, not once per event", () => {
      element.dispatchEvent(new Event("waiting"));
      element.dispatchEvent(new Event("waiting"));

      expect(handler).toHaveBeenCalledTimes(1);
    });

    it.each(["playing", "canplay", "canplaythrough", "pause", "ended", "error", "emptied"])(
      "stops buffering on %s",
      (name) => {
        element.dispatchEvent(new Event("waiting"));
        element.dispatchEvent(new Event(name));

        expect(player.state().buffering).toBe(false);
        expect(handler).toHaveBeenLastCalledWith(expect.objectContaining({ buffering: false }));
      },
    );

    // `stalled` says only that the download stopped. With enough buffered the
    // element plays on and no `playing` follows, so a throbber would stay up.
    it("counts a stall only when the element has too little data to go on", () => {
      pretend(element, "readyState", 4);
      element.dispatchEvent(new Event("stalled"));
      expect(player.state().buffering).toBe(false);

      pretend(element, "readyState", 2);
      element.dispatchEvent(new Event("stalled"));
      expect(player.state().buffering).toBe(true);
    });

    it("ignores a stall while paused", () => {
      player.pause();
      pretend(element, "readyState", 1);
      element.dispatchEvent(new Event("stalled"));

      expect(player.state().buffering).toBe(false);
    });

    it("a new source and a stop both start from not buffering", async () => {
      element.dispatchEvent(new Event("waiting"));
      await player.load({ url: "/rest/stream?id=song-2", trackId: "song-2" });
      expect(player.state().buffering).toBe(false);

      element.dispatchEvent(new Event("waiting"));
      player.stop();
      expect(player.state().buffering).toBe(false);
    });
  });

  describe("the equalizer", () => {
    let context;

    beforeEach(() => {
      equalizer.__resetForTests();
      context = {
        state: "suspended",
        destination: { connect() {} },
        nodes: [],
        resume: vi.fn(),
        createMediaElementSource: vi.fn(() => ({ connect() {}, disconnect() {} })),
        createGain: vi.fn(() => ({ connect() {}, gain: { value: 1 } })),
        createBiquadFilter: vi.fn(() => ({
          connect() {},
          type: "",
          frequency: { value: 0 },
          Q: { value: 0 },
          gain: { value: 0 },
        })),
      };
      equalizer.__setContextFactoryForTests(() => context);
      player.attach(element);
    });

    afterEach(() => {
      equalizer.__resetForTests();
    });

    it("builds no graph for a listener who never switches it on", () => {
      expect(player.setEqualizer({ enabled: false, gains: [], preamp: 0 })).toBe(false);
      expect(context.createMediaElementSource).not.toHaveBeenCalled();
    });

    it("builds the graph around its own element on the first switch-on", () => {
      const applied = player.setEqualizer({
        enabled: true,
        gains: EQ_PRESETS.rock.gains.slice(),
        preamp: EQ_PRESETS.rock.preamp,
      });

      expect(applied).toBe(true);
      expect(context.createMediaElementSource).toHaveBeenCalledWith(element);
    });

    it("cannot build a graph before there is an element", () => {
      player.detach();

      expect(player.setEqualizer({ enabled: true, gains: [], preamp: 0 })).toBe(false);
    });

    it("settings that are missing altogether switch it off", () => {
      expect(player.setEqualizer(undefined)).toBe(false);
    });

    // Browsers suspend contexts on backgrounded tabs, and a suspended context
    // passes no sound at all. Play is the moment that matters.
    it("wakes a suspended audio context up on play", () => {
      player.setEqualizer({ enabled: true, gains: [], preamp: 0 });

      element.dispatchEvent(new Event("play"));

      expect(context.resume).toHaveBeenCalled();
    });
  });

  describe("what the operating system shows", () => {
    let mediaSession;

    beforeEach(() => {
      mediaSession = {
        metadata: null,
        playbackState: "none",
        setPositionState: vi.fn(),
        setActionHandler: vi.fn(),
      };
      Object.defineProperty(navigator, "mediaSession", {
        value: mediaSession,
        configurable: true,
      });
      globalThis.MediaMetadata = class {
        constructor(init) {
          Object.assign(this, init);
        }
      };
      player.attach(element);
    });

    afterEach(() => {
      delete navigator.mediaSession;
      delete globalThis.MediaMetadata;
    });

    it("hands the track to the media session", () => {
      player.setNowPlaying({
        title: "Raise Your Fist",
        artist: "Angerfist",
        album: "Raise Your Fist",
        artworkUrl: "/rest/getCoverArt?id=1",
        duration: 240,
      });

      expect(mediaSession.metadata.title).toBe("Raise Your Fist");
      expect(mediaSession.metadata.artwork[0].src).toBe("/rest/getCoverArt?id=1");
    });

    it("clears it when there is nothing playing", () => {
      player.setNowPlaying({ title: "Raise Your Fist" });
      player.setNowPlaying(null);

      expect(mediaSession.metadata).toBeNull();
    });

    // A chunked stream has no length of its own, and a position state without a
    // duration is refused -- so the length the library reported is the one the
    // lock screen draws its bar from.
    it("reports the position against the length the library gave", () => {
      pretend(element, "duration", Infinity);
      pretend(element, "currentTime", 30);
      player.setNowPlaying({ title: "Raise Your Fist", duration: 240 });

      element.dispatchEvent(new Event("timeupdate"));

      expect(mediaSession.setPositionState).toHaveBeenCalledWith(
        expect.objectContaining({ duration: 240, position: 30 }),
      );
    });

    it("says nothing about a position it cannot place", () => {
      player.setNowPlaying({ title: "Raise Your Fist", duration: 0 });
      mediaSession.setPositionState.mockClear();

      element.dispatchEvent(new Event("timeupdate"));

      expect(mediaSession.setPositionState).not.toHaveBeenCalled();
    });

    it("a media session that refuses a position state does not break playback", () => {
      vi.spyOn(console, "error").mockImplementation(() => {});
      mediaSession.setPositionState = vi.fn(() => {
        throw new TypeError("bad state");
      });
      player.setNowPlaying({ title: "Raise Your Fist", duration: 240 });

      expect(() => element.dispatchEvent(new Event("timeupdate"))).not.toThrow();
    });

    it("follows play and pause, which is what the lock screen draws", () => {
      element.dispatchEvent(new Event("play"));
      expect(mediaSession.playbackState).toBe("playing");

      element.dispatchEvent(new Event("pause"));
      expect(mediaSession.playbackState).toBe("paused");
    });

    // The queue lives in the UI, so a command from outside the app has to come
    // back to it.
    it("routes the transport commands back to the caller", () => {
      const commands = {
        play: vi.fn(),
        pause: vi.fn(),
        next: vi.fn(),
        previous: vi.fn(),
        seekTo: vi.fn(),
      };
      player.setCommandHandlers(commands);

      const handlers = Object.fromEntries(mediaSession.setActionHandler.mock.calls);
      handlers.play();
      handlers.pause();
      handlers.nexttrack();
      handlers.previoustrack();
      handlers.seekto({ seekTime: 90 });

      expect(commands.play).toHaveBeenCalled();
      expect(commands.pause).toHaveBeenCalled();
      expect(commands.next).toHaveBeenCalled();
      expect(commands.previous).toHaveBeenCalled();
      expect(commands.seekTo).toHaveBeenCalledWith(90);
    });

    it("ignores a seek command without a position", () => {
      const seekTo = vi.fn();
      player.setCommandHandlers({ seekTo });

      const handlers = Object.fromEntries(mediaSession.setActionHandler.mock.calls);
      handlers.seekto({});

      expect(seekTo).not.toHaveBeenCalled();
    });

    // Not every browser knows every action; one it refuses must not take the
    // rest of the wiring with it.
    it("survives an action the browser does not know", () => {
      vi.spyOn(console, "warn").mockImplementation(() => {});
      mediaSession.setActionHandler = vi.fn((action) => {
        if (action === "seekto") throw new TypeError("not supported");
      });

      expect(() => player.setCommandHandlers({ play: vi.fn(), seekTo: vi.fn() })).not.toThrow();
    });

    it("clearing the handlers unsets them", () => {
      player.setCommandHandlers(null);

      const handlers = Object.fromEntries(mediaSession.setActionHandler.mock.calls);
      expect(handlers.play).toBeNull();
    });
  });

  describe("without a media session", () => {
    it("does everything the same, minus the operating system", () => {
      player.attach(element);

      expect(() => {
        player.setNowPlaying({ title: "Raise Your Fist", duration: 240 });
        player.setCommandHandlers({ play: vi.fn() });
        element.dispatchEvent(new Event("play"));
        element.dispatchEvent(new Event("timeupdate"));
      }).not.toThrow();
    });
  });
});
