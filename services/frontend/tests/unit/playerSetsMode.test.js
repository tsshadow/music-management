import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import Player from "../../src/lib/Player.svelte";
import {
  credentials,
  currentTrack,
  isMobile,
  mumaApiKey,
  mumaUser,
  nowPlayingOpen,
  playerState,
  playlist,
  radioChannel,
  syncMode,
} from "../../src/lib/store.js";
import { dismissAll, notifications } from "../../src/lib/notifications.js";

/**
 * Sets-mode chrome on the desktop bar: the ±30 s buttons, the h:mm:ss scrub
 * bar and set resume. `playerNativeMode.test.js` is the model for isolating
 * a slice of `Player.svelte` behaviour in its own file; this one stays on
 * the browser engine throughout, like `player.test.js`.
 */

const SONG = { id: "song-1", title: "Raise Your Fist", artist: "Angerfist", duration: 240 };
const SET = { id: "set-1", title: "Defqon Set", artist: "Angerfist", duration: 7200 };

/**
 * A fetch mock covering both the muma `settings/frontend` blob (GET/PATCH) and
 * every other `/rest/*` call (scrobble, rating) with a bare Subsonic "ok".
 *
 * @param {string|null} settingsBlob - What the account already has stored,
 *   as the raw JSON string the real endpoint answers with.
 */
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

describe("Player in sets mode -- desktop chrome", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    playerState.set({ playing: false, repeat: "none", shuffle: false, volume: 50 });
    syncMode.set("off");
    radioChannel.set(null);
    isMobile.set(false);
    nowPlayingOpen.set(false);
    mumaUser.set(null);
    mumaApiKey.set("");
    mockFetch(null);
    window.HTMLMediaElement.prototype.play = vi.fn(async () => {});
    window.HTMLMediaElement.prototype.pause = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    dismissAll();
  });

  it("shows ±30 s buttons for a set, not for a song", () => {
    playlist.set([SET]);
    currentTrack.set(SET);
    renderPlayer();

    expect(screen.getByLabelText("30 seconden terug")).toBeTruthy();
    expect(screen.getByLabelText("30 seconden verder")).toBeTruthy();
  });

  it("has no ±30 s buttons for a song", () => {
    playlist.set([SONG]);
    currentTrack.set(SONG);
    renderPlayer();

    expect(screen.queryByLabelText("30 seconden terug")).toBeNull();
    expect(screen.queryByLabelText("30 seconden verder")).toBeNull();
  });

  it("skips back 30 seconds from wherever the engine actually is", async () => {
    playlist.set([SET]);
    currentTrack.set(SET);
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "duration", { value: 7200, writable: true });
    await fireEvent.loadedMetadata(audioElement);
    audioElement.currentTime = 100;

    await fireEvent.click(screen.getByLabelText("30 seconden terug"));

    expect(audioElement.currentTime).toBe(70);
  });

  it("skips forward 30 seconds, clamped to the track length", async () => {
    playlist.set([SET]);
    currentTrack.set(SET);
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "duration", { value: 7200, writable: true });
    await fireEvent.loadedMetadata(audioElement);
    audioElement.currentTime = 7190;

    await fireEvent.click(screen.getByLabelText("30 seconden verder"));

    expect(audioElement.currentTime).toBe(7200);
  });

  it("shows h:mm:ss rather than m:ss once a set is loaded", async () => {
    playlist.set([SET]);
    currentTrack.set(SET);
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "duration", { value: 7200, writable: true });
    await fireEvent.loadedMetadata(audioElement);
    audioElement.currentTime = 632;
    await fireEvent.timeUpdate(audioElement);

    expect(screen.getByText("0:10:32")).toBeTruthy();
    expect(screen.getByText("2:00:00")).toBeTruthy();
  });

  it("renders the sets-mode scrub bar as a fine-grained range input", () => {
    playlist.set([SET]);
    currentTrack.set(SET);
    renderPlayer();

    const bar = screen.getByLabelText("Door nummer spoelen");
    expect(bar.tagName).toBe("INPUT");
    expect(bar.type).toBe("range");
    expect(bar.step).toBe("1");
  });

  it("keeps the songs-mode click bar -- a div, not a range -- for a plain track", () => {
    playlist.set([SONG]);
    currentTrack.set(SONG);
    renderPlayer();

    const bar = screen.getByLabelText("Door nummer spoelen");
    expect(bar.tagName).toBe("DIV");
  });

  it("dragging the sets-mode bar seeks to the exact second", async () => {
    playlist.set([SET]);
    currentTrack.set(SET);
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "duration", { value: 7200, writable: true });
    await fireEvent.loadedMetadata(audioElement);

    const bar = screen.getByLabelText("Door nummer spoelen");
    await fireEvent.input(bar, { target: { value: "4321" } });

    expect(audioElement.currentTime).toBe(4321);
  });

  it("overrides the sets-mode bar's arrow keys to skip ±30 s instead of the native step", async () => {
    playlist.set([SET]);
    currentTrack.set(SET);
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "duration", { value: 7200, writable: true });
    await fireEvent.loadedMetadata(audioElement);
    audioElement.currentTime = 200;

    const bar = screen.getByLabelText("Door nummer spoelen");
    await fireEvent.keyDown(bar, { key: "ArrowRight" });

    expect(audioElement.currentTime).toBe(230);
  });
});

describe("Player in sets mode -- resume", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    playerState.set({ playing: false, repeat: "none", shuffle: false, volume: 50 });
    syncMode.set("off");
    radioChannel.set(null);
    isMobile.set(false);
    nowPlayingOpen.set(false);
    mumaApiKey.set("test-api-key");
    window.HTMLMediaElement.prototype.play = vi.fn(async () => {});
    window.HTMLMediaElement.prototype.pause = vi.fn();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    dismissAll();
    mumaUser.set(null);
  });

  it("resumes a set from the stored position and offers to start over", async () => {
    mockFetch(JSON.stringify({ setResume: { "track:set-1": { position: 900, updatedAt: 1 } } }));
    mumaUser.set({ id: 7 });
    playlist.set([SET]);
    currentTrack.set(SET);
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "duration", { value: 7200, writable: true });
    await fireEvent.loadedMetadata(audioElement);

    await fireEvent.play(audioElement);

    await waitFor(() => expect(audioElement.currentTime).toBe(900));
    await waitFor(() => expect(get(notifications).length).toBeGreaterThan(0));
    expect(get(notifications)[0].message).toContain("0:15:00");
  });

  it("does not offer to resume a position in the opening minute", async () => {
    mockFetch(JSON.stringify({ setResume: { "track:set-1": { position: 30, updatedAt: 1 } } }));
    mumaUser.set({ id: 7 });
    playlist.set([SET]);
    currentTrack.set(SET);
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "duration", { value: 7200, writable: true });
    await fireEvent.loadedMetadata(audioElement);

    await fireEvent.play(audioElement);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(audioElement.currentTime).toBe(0);
    expect(get(notifications).length).toBe(0);
  });

  it("does not ask twice for the same track once paused and resumed", async () => {
    mockFetch(JSON.stringify({ setResume: { "track:set-1": { position: 900, updatedAt: 1 } } }));
    mumaUser.set({ id: 7 });
    playlist.set([SET]);
    currentTrack.set(SET);
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "duration", { value: 7200, writable: true });
    await fireEvent.loadedMetadata(audioElement);

    await fireEvent.play(audioElement);
    await waitFor(() => expect(get(notifications).length).toBe(1));

    audioElement.currentTime = 950;
    await fireEvent.pause(audioElement);
    await fireEvent.play(audioElement);
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(get(notifications).length).toBe(1);
  });

  it("writes the position on pause", async () => {
    mockFetch(null);
    mumaUser.set({ id: 7 });
    playlist.set([SET]);
    currentTrack.set(SET);
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "duration", { value: 7200, writable: true });
    await fireEvent.loadedMetadata(audioElement);
    audioElement.currentTime = 1234;

    await fireEvent.pause(audioElement);

    await waitFor(() => expect(setResumeWriteBody()).toBeTruthy());
    const body = setResumeWriteBody();
    expect(body.setResume["track:set-1"].position).toBe(1234);
  });

  it("throttles periodic writes to once every 15 seconds while playing", async () => {
    vi.useFakeTimers();
    mockFetch(null);
    mumaUser.set({ id: 7 });
    playlist.set([SET]);
    currentTrack.set(SET);
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "duration", { value: 7200, writable: true });
    await fireEvent.loadedMetadata(audioElement);

    audioElement.currentTime = 100;
    await fireEvent.timeUpdate(audioElement);
    await vi.advanceTimersByTimeAsync(0);
    const writesSoFar = () =>
      global.fetch.mock.calls.filter(([, opts]) => opts?.method === "PATCH").length;
    const firstBatch = writesSoFar();

    audioElement.currentTime = 105;
    await fireEvent.timeUpdate(audioElement);
    await vi.advanceTimersByTimeAsync(0);
    expect(writesSoFar()).toBe(firstBatch);

    await vi.advanceTimersByTimeAsync(15001);
    audioElement.currentTime = 130;
    await fireEvent.timeUpdate(audioElement);
    await vi.advanceTimersByTimeAsync(0);
    expect(writesSoFar()).toBeGreaterThan(firstBatch);
  });

  it("writes the outgoing set's position on a track change, not the new track's", async () => {
    mockFetch(null);
    mumaUser.set({ id: 7 });
    playlist.set([SET, SONG]);
    currentTrack.set(SET);
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "duration", { value: 7200, writable: true });
    await fireEvent.loadedMetadata(audioElement);
    audioElement.currentTime = 2000;

    currentTrack.set(SONG);
    await waitFor(() => expect(setResumeWriteBody()).toBeTruthy());
    const body = setResumeWriteBody();
    expect(body.setResume["track:set-1"].position).toBe(2000);
  });
});

/**
 * The most recent PATCH to the settings blob that actually carries a
 * `setResume` key -- `mumaUser.set(...)` above also triggers the unrelated
 * favourite-genres/language account sync, which PATCHes the same endpoint,
 * so picking the first or last PATCH regardless of its body is not reliable.
 */
function setResumeWriteBody() {
  const bodies = global.fetch.mock.calls
    .filter(([, opts]) => opts?.method === "PATCH")
    .map(([, opts]) => JSON.parse(opts.body).set);
  return bodies.reverse().find((body) => body.setResume);
}
