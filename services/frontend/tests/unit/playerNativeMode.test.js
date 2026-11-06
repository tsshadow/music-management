import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from "vitest";
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
  startStation: vi.fn(async () => ({})),
  stopRadio: vi.fn(async () => ({})),
  toggleNews: vi.fn(async () => ({})),
  pause: vi.fn(async () => ({})),
  next: vi.fn(async () => ({})),
  previous: vi.fn(async () => ({})),
});

// The output the phone plays through (increment H of phone-ui-polish), answered once on mount
// and then pushed through `outputRouteChanged`.
const systemPlugin = fakePlugin({
  outputRoute: vi.fn(async () => ({ name: "Bose QC35 II", type: "bluetooth" })),
  openOutputPicker: vi.fn(async () => ({})),
});

const plugins = {
  MumaPlayer: playerPlugin,
  MumaStorage: fakePlugin(),
  MumaSpeech: fakePlugin(),
  MumaDiagnostics: fakePlugin(),
  MumaSystem: systemPlugin,
};

vi.mock("@capacitor/core", () => ({
  registerPlugin: (name) => plugins[name],
}));

window.Capacitor = { isNativePlatform: () => true };

const { default: Player } = await import("../../src/lib/Player.svelte");
const {
  credentials,
  currentTrack,
  isMobile,
  liveStation,
  nowPlayingOpen,
  playerState,
  playlist,
  radioChannel,
  syncMode,
} = await import("../../src/lib/store.js");
const { dismissAll } = await import("../../src/lib/notifications.js");
// Imported after the platform mocks above, like the component. Now Playing is its own chunk
// (issue #119): loaded up front so the tests that open it see the real view on the first frame,
// not its seeded shell (issue #120).
const { LAZY_HOOK_TIMEOUT_MS, loadLazy } = await import("./lazyTestUtils.js");
beforeAll(() => loadLazy("nowPlaying"), LAZY_HOOK_TIMEOUT_MS);

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
    systemPlugin.outputRoute.mockClear();
    systemPlugin.openOutputPicker.mockClear();
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
  // Since bug report 095 the button does not pick a track at all: it asks the service for
  // "next", and the service applies its own shuffle order. The UI moves when the service reports.
  it("does not walk a shuffle trail for the on-screen next button", async () => {
    playerState.update((s) => ({ ...s, shuffle: true }));
    playerPlugin.next.mockClear();
    renderPlayer();

    await fireEvent.click(screen.getByLabelText("Volgende"));

    expect(playerPlugin.next).toHaveBeenCalledTimes(1);
    expect(get(currentTrack)).toEqual(FIRST);
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

  // The service scrobbles every track itself (source `mobile`/`auto`). A second scrobble from the
  // WebView recorded each listen twice on production, under timestamps the server cannot pair.
  it("leaves scrobbling to the service -- no /rest/scrobble from the WebView", async () => {
    credentials.set({ url: "", username: "demo-user", password: "pw" });
    global.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok" } }),
    }));
    renderPlayer();

    playerPlugin.fire("play", { status: "playing", trackId: FIRST.id, position: 0, duration: 240 });
    playerPlugin.fire("timeupdate", {
      status: "playing",
      trackId: FIRST.id,
      position: 200,
      duration: 240,
    });
    playerPlugin.fire("ended", { status: "ended", trackId: FIRST.id });
    await new Promise((resolve) => setTimeout(resolve, 0));

    const urls = global.fetch.mock.calls.map(([url]) => String(url));
    expect(urls.filter((url) => url.includes("/rest/scrobble"))).toEqual([]);
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
  describe("audio output", () => {
    async function openNowPlaying() {
      isMobile.set(true);
      renderPlayer();
      await fireEvent.click(screen.getByText("Raise Your Fist"));
      return screen.getByTestId("now-playing");
    }

    it("reads the route once on mount and names it on the player screen", async () => {
      await openNowPlaying();

      await waitFor(() =>
        expect(screen.getByTestId("now-playing-output").textContent).toContain("Bose QC35 II"),
      );
      expect(systemPlugin.outputRoute).toHaveBeenCalledTimes(1);
    });

    it("follows an outputRouteChanged event", async () => {
      await openNowPlaying();
      await waitFor(() => screen.getByTestId("now-playing-output"));

      systemPlugin.fire("outputRouteChanged", { name: "Phone speaker", type: "speaker" });

      await waitFor(() =>
        expect(screen.getByTestId("now-playing-output").textContent).toContain("Phone speaker"),
      );
    });

    it("opens the system picker from the label", async () => {
      await openNowPlaying();
      const label = await waitFor(() => screen.getByTestId("now-playing-output"));

      await fireEvent.click(label);

      expect(systemPlugin.openOutputPicker).toHaveBeenCalledTimes(1);
    });

    it("hides the label while the shell has not named a route", async () => {
      systemPlugin.outputRoute.mockResolvedValueOnce({});
      await openNowPlaying();
      // Let the resolved (empty) answer land before asserting on its absence.
      await new Promise((resolve) => setTimeout(resolve, 0));

      expect(screen.queryByTestId("now-playing-output")).toBeNull();
    });
  });

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

    it("tunes into a station through the service, not the web view", async () => {
      globalThis.fetch = vi.fn(async (url) => {
        if (String(url).includes("/api/radio/stations")) {
          return {
            ok: true,
            json: async () => ({
              stations: [{ slug: "slam", name: "SLAM", stream_url: "https://example.com/s.mp3" }],
            }),
          };
        }
        return {
          ok: true,
          json: async () => ({ channels: [{ slug: "main", name: "MuMa Radio" }] }),
        };
      });
      renderPlayer();

      await fireEvent.click(screen.getByLabelText("Radio"));
      await waitFor(() => expect(screen.getByText("SLAM")).toBeTruthy());
      await fireEvent.click(screen.getByText("SLAM"));

      await waitFor(() => expect(playerPlugin.startStation).toHaveBeenCalledWith({ slug: "slam" }));
      liveStation.set(null);
    });

    it("follows a station started in the car, and shows what the stream sends", async () => {
      renderPlayer();

      playerPlugin.fire("timeupdate", {
        stationSlug: "slam",
        stationTitle: "Angerfist - Pissed Off",
      });
      await waitFor(() => expect(get(liveStation)?.slug).toBe("slam"));
      expect(get(liveStation).title).toBe("Angerfist - Pissed Off");

      playerPlugin.fire("timeupdate", { stationSlug: null, stationTitle: null });
      await waitFor(() => expect(get(liveStation)).toBeNull());
    });

    // Two starts in flight at once used to both run to completion: the one that finished last
    // decided which channel the display showed, whatever the listener picked last.
    it("a channel picked while another is still tuning in wins, whichever answers first", async () => {
      const channels = [
        { slug: "main", name: "Hoofdzender" },
        { slug: "other", name: "Tweede zender" },
      ];
      global.fetch = vi.fn(async (url) => {
        if (String(url).includes("/api/radio/channels")) {
          return { ok: true, json: async () => ({ channels }) };
        }
        if (String(url).includes("/api/radio/time")) {
          return { ok: true, json: async () => ({ server_time: Date.now() / 1000 }) };
        }
        return { ok: true, json: async () => ({ current: null, next: null }) };
      });
      const pending = [];
      playerPlugin.startRadio.mockImplementation(
        () => new Promise((resolve) => pending.push(resolve)),
      );
      renderPlayer();

      await fireEvent.click(screen.getByLabelText("Radio"));
      await fireEvent.click(await screen.findByText("Hoofdzender"));
      await fireEvent.click(screen.getByLabelText("Radio"));
      await fireEvent.click(await screen.findByText("Tweede zender"));
      await waitFor(() => expect(pending).toHaveLength(2));

      pending[1]({});
      await waitFor(() => expect(get(radioChannel)).toBe("other"));
      pending[0]({});
      await new Promise((resolve) => setTimeout(resolve, 0));

      expect(get(radioChannel)).toBe("other");
      playerPlugin.startRadio.mockImplementation(async () => ({}));
    });

    it("a second tap on the channel that is still tuning in does not start it twice", async () => {
      global.fetch = vi.fn(async (url) => {
        if (String(url).includes("/api/radio/channels")) {
          return {
            ok: true,
            json: async () => ({ channels: [{ slug: "main", name: "Radio" }] }),
          };
        }
        if (String(url).includes("/api/radio/time")) {
          return { ok: true, json: async () => ({ server_time: Date.now() / 1000 }) };
        }
        return { ok: true, json: async () => ({ current: null, next: null }) };
      });
      const pending = [];
      playerPlugin.startRadio.mockImplementation(
        () => new Promise((resolve) => pending.push(resolve)),
      );
      renderPlayer();

      await fireEvent.click(screen.getByLabelText("Radio"));
      await fireEvent.click(screen.getByLabelText("Radio"));
      await waitFor(() => expect(pending).toHaveLength(1));
      await new Promise((resolve) => setTimeout(resolve, 0));
      pending[0]({});
      await waitFor(() => expect(get(radioChannel)).toBe("main"));

      expect(playerPlugin.startRadio).toHaveBeenCalledTimes(1);
      playerPlugin.startRadio.mockImplementation(async () => ({}));
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
