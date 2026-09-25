import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { resetRatings } from "../../src/lib/ratings.js";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import TrackList from "../../src/lib/TrackList.svelte";
import { notify, dismissAll } from "../../src/lib/notifications.js";

const track = (extra = {}) => ({
  id: "1",
  title: "Track",
  artist: "Artist",
  album: "Album",
  albumId: "a1",
  duration: 200,
  ...extra,
});

describe("TrackList rating", () => {
  beforeEach(() => {
    resetRatings();
    dismissAll();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    dismissAll();
  });

  // Subsonic rejects with a 200, which is exactly what used to pass as a
  // success here -- the star stayed lit and nothing was saved.
  it("reports a rejected rating and puts the old one back", async () => {
    const spy = vi.spyOn(notify, "error");
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": { status: "failed", error: { code: 50, message: "Not authorized" } },
      }),
    }));
    const subject = track({ userRating: 3 });
    render(TrackList, { tracks: [subject], onnavigate: vi.fn() });

    await fireEvent.click(screen.getAllByLabelText("5 sterren")[0]);

    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls[0][0]).toBe("Beoordeling kon niet worden opgeslagen");
    expect(subject.userRating).toBe(3);
  });

  it("says nothing when the rating is accepted", async () => {
    const spy = vi.spyOn(notify, "error");
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok" } }),
    }));
    const subject = track({ userRating: 3 });
    render(TrackList, { tracks: [subject], onnavigate: vi.fn() });

    await fireEvent.click(screen.getAllByLabelText("5 sterren")[0]);

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/rest/setRating"))).toBe(
        true,
      ),
    );
    expect(spy).not.toHaveBeenCalled();
    expect(subject.userRating).toBe(5);
  });
});
