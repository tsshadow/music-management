import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render } from "@testing-library/svelte";
import { get } from "svelte/store";
import Player from "../../src/lib/Player.svelte";
import {
  audio,
  credentials,
  currentTrack,
  equalizerSettings,
  isMobile,
  playerState,
  playlist,
  radioChannel,
  syncMode,
} from "../../src/lib/store.js";
import * as equalizer from "../../src/lib/equalizer.js";
import { EQ_PRESETS } from "../../src/lib/equalizerPresets.js";

const TRACK = {
  id: "song-1",
  title: "Raise Your Fist",
  artist: "Angerfist",
  artistId: "artist-1",
  albumId: "album-1",
  duration: 240,
};

function fakeContext() {
  return {
    state: "running",
    destination: { connect() {} },
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
}

/**
 * The component and the engine, wired together.
 *
 * The Player tests cover what the listener sees; these cover the hand-off the
 * platform adapter introduced, which is invisible until it is wrong -- and when
 * it is wrong, the symptom is a player that looks perfect and makes no sound.
 */
describe("Player and the playback engine", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    playlist.set([TRACK]);
    currentTrack.set(TRACK);
    playerState.set({ playing: false, repeat: "none", shuffle: false, volume: 50, progress: 0 });
    syncMode.set("off");
    radioChannel.set(null);
    isMobile.set(false);
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok" } }),
    }));
    window.HTMLMediaElement.prototype.play = vi.fn(async () => {});
    window.HTMLMediaElement.prototype.pause = vi.fn();
    equalizer.__resetForTests();
  });

  afterEach(() => {
    equalizer.__resetForTests();
    vi.restoreAllMocks();
  });

  it("hands its element to the engine, which publishes it", () => {
    const { container } = render(Player, { onnavigate: vi.fn(), ontoggleQueue: vi.fn() });

    expect(get(audio)).toBe(container.querySelector("audio"));
  });

  it("lets go of the element again when the player goes away", () => {
    const { unmount } = render(Player, { onnavigate: vi.fn(), ontoggleQueue: vi.fn() });

    unmount();

    expect(get(audio)).toBeNull();
  });

  it("starts at the volume the listener left it at", () => {
    playerState.update((s) => ({ ...s, volume: 30 }));

    const { container } = render(Player, { onnavigate: vi.fn(), ontoggleQueue: vi.fn() });

    expect(container.querySelector("audio").volume).toBeCloseTo(0.3);
  });

  // The equalizer effect runs before the element has been handed over, so a
  // curve that is already switched on has to be applied once the engine has
  // something to build its graph around. Without that, a listener who turns the
  // equalizer on and reloads the page gets a flat sound and no way to tell.
  it("builds the graph for a curve that was already switched on", async () => {
    const context = fakeContext();
    equalizer.__setContextFactoryForTests(() => context);
    equalizerSettings.set({
      enabled: true,
      preamp: EQ_PRESETS.rock.preamp,
      gains: EQ_PRESETS.rock.gains.slice(),
      preset: "rock",
    });

    const { container } = render(Player, { onnavigate: vi.fn(), ontoggleQueue: vi.fn() });
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(context.createMediaElementSource).toHaveBeenCalledWith(container.querySelector("audio"));
  });

  it("loads the track that was playing without starting it", () => {
    const { container } = render(Player, { onnavigate: vi.fn(), ontoggleQueue: vi.fn() });

    expect(container.querySelector("audio").getAttribute("src")).toContain(
      "/rest/stream?id=song-1",
    );
    expect(window.HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  });
});
