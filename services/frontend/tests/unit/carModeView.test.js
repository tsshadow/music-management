import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, fireEvent, waitFor, screen } from "@testing-library/svelte";
import { get } from "svelte/store";
import CarModeView from "../../src/lib/CarModeView.svelte";
import { platform } from "../../src/lib/platform/index.js";
import {
  credentials,
  currentTrack,
  playlist,
  favoriteGenres,
  playerState,
} from "../../src/lib/store.js";

/**
 * The driving screen. `platform.player` is spied on rather than driven through a fake bridge --
 * this is the same browser implementation `Player.svelte` uses in every other test file, and the
 * point here is only that the view calls the right method with the right arguments, not that the
 * engine itself behaves (that is `platformPlayer.test.js`'s job).
 */

const TRACK = { id: "42", title: "Follow Me", artist: "Ran-D", coverArt: "cover-1", userRating: 3 };

function fetchMock() {
  return vi.fn(async (url) => {
    if (url.includes("/rest/setRating")) {
      return { ok: true, json: async () => ({ "subsonic-response": { status: "ok" } }) };
    }
    if (url.includes("/rest/getSongs")) {
      return {
        ok: true,
        json: async () => ({
          "subsonic-response": { songs: { song: [{ id: "7", title: "Mix track" }] } },
        }),
      };
    }
    return { ok: true, json: async () => ({ "subsonic-response": { status: "ok" } }) };
  });
}

describe("CarModeView", () => {
  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "user", password: "pw" });
    currentTrack.set({ ...TRACK });
    playlist.set([]);
    favoriteGenres.set(["Hardcore"]);
    playerState.set({ playing: false, volume: 100, progress: 0, duration: 0 });
    globalThis.fetch = fetchMock();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the current track", async () => {
    render(CarModeView, { onclose: vi.fn(), onmicrophone: vi.fn() });

    expect(await screen.findByText("Follow Me")).toBeTruthy();
    expect(screen.getByText("Ran-D")).toBeTruthy();
  });

  it("plays when paused and pauses when playing", async () => {
    const play = vi.spyOn(platform.player, "play").mockResolvedValue();
    const pause = vi.spyOn(platform.player, "pause").mockImplementation(() => {});
    vi.spyOn(platform.player, "state").mockReturnValue({ status: "paused" });

    const { getByLabelText } = render(CarModeView, { onclose: vi.fn(), onmicrophone: vi.fn() });
    await fireEvent.click(getByLabelText("Afspelen"));

    expect(play).toHaveBeenCalledOnce();
    expect(pause).not.toHaveBeenCalled();
  });

  it("asks the native queue to move, rather than deciding the next track itself", async () => {
    const next = vi.spyOn(platform.player, "next").mockImplementation(() => {});
    const previous = vi.spyOn(platform.player, "previous").mockImplementation(() => {});

    const { getByLabelText } = render(CarModeView, { onclose: vi.fn(), onmicrophone: vi.fn() });
    await fireEvent.click(getByLabelText("Volgende"));
    await fireEvent.click(getByLabelText("Vorige"));

    expect(next).toHaveBeenCalledOnce();
    expect(previous).toHaveBeenCalledOnce();
  });

  it("rates the current track and updates it optimistically", async () => {
    const { getByLabelText } = render(CarModeView, { onclose: vi.fn(), onmicrophone: vi.fn() });

    await fireEvent.click(getByLabelText("Beoordeel met 5 sterren"));

    expect(get(currentTrack).userRating).toBe(5);
    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/rest/setRating?id=42&rating=5"),
      ),
    );
  });

  it("tapping the current rating again clears it, the same toggle the track list uses", async () => {
    const { getByLabelText } = render(CarModeView, { onclose: vi.fn(), onmicrophone: vi.fn() });

    await fireEvent.click(getByLabelText("Beoordeel met 3 sterren"));

    expect(get(currentTrack).userRating).toBe(0);
  });

  it("rolls the rating back when the server refuses it", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ "subsonic-response": { status: "failed", error: { message: "nope" } } }),
    }));

    const { getByLabelText } = render(CarModeView, { onclose: vi.fn(), onmicrophone: vi.fn() });
    await fireEvent.click(getByLabelText("Beoordeel met 5 sterren"));

    await waitFor(() => expect(get(currentTrack).userRating).toBe(3));
  });

  it("starts a shuffled favourites mix", async () => {
    render(CarModeView, { onclose: vi.fn(), onmicrophone: vi.fn() });

    await fireEvent.click(await screen.findByText("Favorieten-mix"));

    await waitFor(() => expect(get(playlist)).toEqual([{ id: "7", title: "Mix track" }]));
    const [mixUrl] = globalThis.fetch.mock.calls.find(([url]) => url.includes("getSongs"));
    expect(mixUrl).toContain("ratingMin=4");
  });

  it("starts a genre mix from the account's favourite genres", async () => {
    render(CarModeView, { onclose: vi.fn(), onmicrophone: vi.fn() });

    await fireEvent.click(await screen.findByText("Hardcore-mix"));

    await waitFor(() => expect(get(currentTrack)).toEqual({ id: "7", title: "Mix track" }));
    const [mixUrl] = globalThis.fetch.mock.calls.find(([url]) => url.includes("getSongs"));
    expect(decodeURIComponent(mixUrl)).toContain('"name":"GENRE","value":["Hardcore"]');
  });

  it("closes through the caller and asks for the microphone through the caller", async () => {
    const onclose = vi.fn();
    const onmicrophone = vi.fn();
    const { getByLabelText } = render(CarModeView, { onclose, onmicrophone });

    await fireEvent.click(getByLabelText("Sluiten"));
    await fireEvent.click(getByLabelText("Spraakzoekopdracht"));

    expect(onclose).toHaveBeenCalledOnce();
    expect(onmicrophone).toHaveBeenCalledOnce();
  });

  it("asks the shell to keep the screen on while mounted and releases it on the way out", async () => {
    const setKeepScreenOn = vi.spyOn(platform.system, "setKeepScreenOn").mockResolvedValue();

    const { unmount } = render(CarModeView, { onclose: vi.fn(), onmicrophone: vi.fn() });
    await waitFor(() =>
      expect(setKeepScreenOn).toHaveBeenCalledWith({ showWhenLocked: true, turnScreenOn: true }),
    );

    unmount();

    expect(setKeepScreenOn).toHaveBeenLastCalledWith({
      showWhenLocked: false,
      turnScreenOn: false,
    });
  });
});
