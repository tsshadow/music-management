import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/svelte";
import TrackList from "../../src/lib/TrackList.svelte";
import { queuePosition, queuePositionWidth } from "../../src/lib/queuePosition.js";
import {
  credentials,
  currentTrack,
  isMobile,
  playlist,
  trackListLines,
} from "../../src/lib/store.js";

const tracks = ["a", "b", "c"].map((id, n) => ({
  id,
  title: `Title ${id}`,
  artist: "Artist",
  album: "Album",
  duration: 100 + n,
  suffix: "mp3",
}));

describe("queuePosition", () => {
  it("counts from one over the queue length", () => {
    expect(queuePosition(0, 500)).toBe("1/500");
    expect(queuePosition(2, 500)).toBe("3/500");
  });

  it("sizes the column to the last row", () => {
    expect(queuePositionWidth(500)).toBe(7);
    expect(queuePositionWidth(9)).toBe(3);
  });
});

describe("TrackList queue position", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "demo-user", password: "pw" });
    playlist.set(tracks);
    currentTrack.set(null);
    isMobile.set(true);
    trackListLines.set(3);
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
  });

  it("shows the position in list order on every queue row", () => {
    render(TrackList, { tracks, isQueue: true, onnavigate: vi.fn() });
    expect(screen.getAllByTestId("queue-position").map((e) => e.textContent)).toEqual([
      "1/3",
      "2/3",
      "3/3",
    ]);
  });

  it("follows a reordered queue", () => {
    render(TrackList, {
      tracks: [tracks[2], tracks[0], tracks[1]],
      isQueue: true,
      onnavigate: vi.fn(),
    });
    const rows = document.querySelectorAll("tr[data-track-id]");
    expect(rows[0].getAttribute("data-track-id")).toBe("c");
    expect(rows[0].querySelector('[data-testid="queue-position"]').textContent).toBe("1/3");
  });

  it("puts the date on the album line, right of the album", () => {
    render(TrackList, { tracks, isQueue: true, onnavigate: vi.fn() });
    expect(screen.getAllByTestId("queue-date")).toHaveLength(3);
  });

  it("adds no position outside the queue", () => {
    render(TrackList, { tracks, onnavigate: vi.fn() });
    expect(screen.queryAllByTestId("queue-position")).toHaveLength(0);
  });
});
