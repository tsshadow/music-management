import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, fireEvent, waitFor, screen } from "@testing-library/svelte";
import { get } from "svelte/store";
import TrackList from "../../src/lib/TrackList.svelte";
import CarModeView from "../../src/lib/CarModeView.svelte";
import {
  credentials,
  currentTrack,
  playlist,
  playerState,
  favoriteGenres,
} from "../../src/lib/store.js";
import {
  ratings,
  ratingOf,
  setRating,
  clearRating,
  tapStar,
  resetRatings,
} from "../../src/lib/ratings.js";
import { notify, dismissAll } from "../../src/lib/notifications.js";
import { offline } from "../../src/lib/subsonic.js";

/**
 * The shared rating store: one write path, one place every view reads from. The component tests
 * for each view (`trackListRating`, `player`, `carModeView`) cover their own rows; this file pins
 * the store's contract and that a rating set in one view repaints another.
 */

const ok = () => ({ ok: true, json: async () => ({ "subsonic-response": { status: "ok" } }) });
const refused = () => ({
  ok: true,
  json: async () => ({
    "subsonic-response": { status: "failed", error: { code: 50, message: "nope" } },
  }),
});

/** A fetch whose answer the test releases by hand, to look at the state in between. */
function deferredFetch() {
  const calls = [];
  const impl = vi.fn(
    (url) =>
      new Promise((resolve) => {
        calls.push({ url, resolve });
      }),
  );
  return { impl, calls };
}

describe("ratings store", () => {
  beforeEach(() => {
    resetRatings();
    dismissAll();
    credentials.set({ url: "https://lms.example", username: "demo-user", password: "pw" });
    currentTrack.set(null);
    offline.set(false);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    dismissAll();
    offline.set(false);
  });

  it("falls back to the rating the server sent until something is written", () => {
    expect(ratingOf(get(ratings), { id: "1", userRating: 4 })).toBe(4);
    expect(ratingOf(get(ratings), { id: "1" })).toBe(0);
    expect(ratingOf(get(ratings), null)).toBe(0);
  });

  // Issue #256: the phone's player holds its own copy of the queue, and the car's rating button
  // starts from it. It hears about every rating, and about a rollback too, but writes nothing.
  it("tells the phone's player about a rating, and about a rollback", async () => {
    const setRatingOnPlayer = vi.fn(async () => {});
    const platform = { player: { setRating: setRatingOnPlayer } };

    await setRating("7", 4, { fetchImpl: vi.fn(async () => ok()), platform, previous: 2 });
    expect(setRatingOnPlayer).toHaveBeenCalledWith("7", 4);

    setRatingOnPlayer.mockClear();
    await setRating("7", 5, { fetchImpl: vi.fn(async () => refused()), platform, previous: 4 });
    expect(setRatingOnPlayer.mock.calls).toEqual([
      ["7", 5],
      ["7", 4],
    ]);
  });

  it("still writes the rating when the player cannot be told", async () => {
    const platform = {
      player: {
        setRating: vi.fn(async () => {
          throw new Error("not implemented");
        }),
      },
    };
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const fetchImpl = vi.fn(async () => ok());

    await expect(setRating("8", 3, { fetchImpl, platform, previous: 0 })).resolves.toBe(true);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
    expect(get(ratings)["8"]).toBe(3);
    await Promise.resolve();
    expect(warn).toHaveBeenCalled();
  });

  it("shows the new rating before the server has answered", async () => {
    const { impl, calls } = deferredFetch();
    const done = setRating("1", 5, { fetchImpl: impl, previous: 2 });

    expect(get(ratings)["1"]).toBe(5);
    expect(calls[0].url).toContain("/rest/setRating?id=1&rating=5");

    calls[0].resolve(ok());
    await expect(done).resolves.toBe(true);
    expect(get(ratings)["1"]).toBe(5);
  });

  it("rolls back and tells the user when the server refuses", async () => {
    const spy = vi.spyOn(notify, "error");
    const stored = await setRating("1", 5, {
      fetchImpl: vi.fn(async () => refused()),
      previous: 2,
    });

    expect(stored).toBe(false);
    expect(get(ratings)["1"]).toBe(2);
    expect(spy).toHaveBeenCalledWith("Beoordeling kon niet worden opgeslagen", { detail: "nope" });
  });

  it("rolls back when the server cannot be reached", async () => {
    const stored = await setRating("1", 4, {
      fetchImpl: vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
      previous: 1,
    });

    expect(stored).toBe(false);
    expect(get(ratings)["1"]).toBe(1);
  });

  describe("the phone's rating queue (docs/designs/offline-followups/)", () => {
    /** A platform whose phone queue accepts everything, as the app's does. */
    const phone = () => ({ storage: { queueRating: vi.fn(async () => true) } });
    const unreachable = () =>
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      });

    it("queues on the phone in offline mode, without a request, and keeps the stars", async () => {
      offline.set(true);
      const platform = phone();
      const fetchImpl = vi.fn(async () => ok());
      const info = vi.spyOn(notify, "info");

      const stored = await setRating("7", 4, { fetchImpl, platform, previous: 1 });

      expect(stored).toBe(true);
      expect(fetchImpl).not.toHaveBeenCalled();
      expect(platform.storage.queueRating).toHaveBeenCalledWith("7", 4);
      expect(get(ratings)["7"]).toBe(4);
      expect(info).toHaveBeenCalledWith(
        "Beoordeling bewaard, gaat naar de server zodra die weer bereikbaar is",
      );
    });

    it("queues a clear in offline mode as rating 0", async () => {
      offline.set(true);
      const platform = phone();

      await clearRating("7", { fetchImpl: vi.fn(), platform, previous: 3 });

      expect(platform.storage.queueRating).toHaveBeenCalledWith("7", 0);
      expect(get(ratings)["7"]).toBe(0);
    });

    it("queues when the request never reached the server", async () => {
      const platform = phone();

      const stored = await setRating("8", 5, { fetchImpl: unreachable(), platform, previous: 2 });

      expect(stored).toBe(true);
      expect(platform.storage.queueRating).toHaveBeenCalledWith("8", 5);
      expect(get(ratings)["8"]).toBe(5);
    });

    it("queues when only the proxy answered (502)", async () => {
      const platform = phone();
      const fetchImpl = vi.fn(async () => ({ ok: false, status: 502, statusText: "Bad Gateway" }));

      expect(await setRating("9", 3, { fetchImpl, platform, previous: 0 })).toBe(true);
      expect(platform.storage.queueRating).toHaveBeenCalledWith("9", 3);
    });

    it("rolls back, without queueing, when the server refuses", async () => {
      const platform = phone();

      const stored = await setRating("1", 5, {
        fetchImpl: vi.fn(async () => refused()),
        platform,
        previous: 2,
      });

      expect(stored).toBe(false);
      expect(platform.storage.queueRating).not.toHaveBeenCalled();
      expect(get(ratings)["1"]).toBe(2);
    });

    it("rolls back when the phone has no queue (an older APK)", async () => {
      const platform = {
        storage: {
          queueRating: vi.fn(async () => {
            throw new Error("not implemented");
          }),
        },
      };

      expect(await setRating("1", 4, { fetchImpl: unreachable(), platform, previous: 1 })).toBe(
        false,
      );
      expect(get(ratings)["1"]).toBe(1);
    });

    it("sends a later rating of a queued track through the queue too, so the last one wins", async () => {
      const platform = phone();
      await setRating("5", 2, { fetchImpl: unreachable(), platform, previous: 0 });

      const fetchImpl = vi.fn(async () => ok());
      await setRating("5", 5, { fetchImpl, platform });

      expect(fetchImpl).not.toHaveBeenCalled();
      expect(platform.storage.queueRating).toHaveBeenLastCalledWith("5", 5);
    });
  });

  it("does not let a late failure undo a newer rating", async () => {
    const { impl, calls } = deferredFetch();
    const first = setRating("1", 3, { fetchImpl: impl, previous: 0 });
    const second = setRating("1", 5, { fetchImpl: impl });

    calls[1].resolve(ok());
    await second;
    calls[0].resolve(refused());
    await first;

    expect(get(ratings)["1"]).toBe(5);
  });

  it("keeps the current track in step, which the native session and car mode read", async () => {
    currentTrack.set({ id: "1", title: "x", userRating: 2 });

    await setRating("1", 5, { fetchImpl: vi.fn(async () => ok()) });

    expect(get(currentTrack).userRating).toBe(5);
  });

  it("refuses a value outside 1-5 without a request; clearing is its own call", async () => {
    const fetchImpl = vi.fn(async () => ok());

    await expect(setRating("1", 0, { fetchImpl })).rejects.toThrow(RangeError);
    await expect(setRating("1", 6, { fetchImpl })).rejects.toThrow(RangeError);
    expect(fetchImpl).not.toHaveBeenCalled();

    await clearRating("1", { fetchImpl, previous: 3 });
    expect(fetchImpl.mock.calls[0][0]).toContain("rating=0");
    expect(get(ratings)["1"]).toBe(0);
  });

  it("a tap on one star rates 1 -- it never deletes -- and a tap on the lit star clears", async () => {
    const fetchImpl = vi.fn(async () => ok());
    const track = { id: "1", userRating: 0 };

    await tapStar(track, 1, { fetchImpl });
    expect(fetchImpl.mock.calls[0][0]).toContain("rating=1");
    expect(get(ratings)["1"]).toBe(1);

    await tapStar(track, 1, { fetchImpl });
    expect(fetchImpl.mock.calls[1][0]).toContain("rating=0");
    expect(get(ratings)["1"]).toBe(0);
  });
});

describe("one rating, every view", () => {
  const TRACK = {
    id: "42",
    title: "Follow Me",
    artist: "Ran-D",
    album: "A",
    albumId: "a1",
    duration: 200,
    userRating: 3,
  };

  beforeEach(() => {
    resetRatings();
    dismissAll();
    credentials.set({ url: "https://lms.example", username: "demo-user", password: "pw" });
    currentTrack.set({ ...TRACK });
    playlist.set([]);
    favoriteGenres.set([]);
    playerState.set({ playing: false, volume: 100, progress: 0, duration: 0 });
    globalThis.fetch = vi.fn(async () => ok());
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("a rating set in the track list repaints car mode without a reload", async () => {
    render(CarModeView, { onclose: vi.fn(), onmicrophone: vi.fn() });
    // A separate object: the list's track is not the current-track store's object.
    render(TrackList, { tracks: [{ ...TRACK }], onnavigate: vi.fn() });

    const carStar = screen.getByLabelText("Beoordeel met 5 sterren");
    expect(carStar.className).toContain("text-white/20");

    await fireEvent.click(screen.getAllByLabelText("5 sterren")[0]);

    await waitFor(() => expect(carStar.className).toContain("text-brand"));
    expect(get(currentTrack).userRating).toBe(5);
  });

  it("a rating set in car mode repaints the track list, and a refusal rolls both back", async () => {
    globalThis.fetch = vi.fn(async () => refused());
    render(TrackList, { tracks: [{ ...TRACK }], onnavigate: vi.fn() });
    render(CarModeView, { onclose: vi.fn(), onmicrophone: vi.fn() });

    const listStar = screen.getAllByLabelText("5 sterren")[0];
    await fireEvent.click(screen.getByLabelText("Beoordeel met 5 sterren"));

    await waitFor(() => expect(get(ratings)["42"]).toBe(3));
    expect(listStar.className).not.toContain("text-brand");
  });
});
