import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/svelte";
import TrackList from "../../src/lib/TrackList.svelte";
import { isMobile } from "../../src/lib/store.js";

const track = (extra = {}) => ({
  id: "1",
  title: "Track",
  artist: "Artist",
  album: "Album",
  albumId: "a1",
  duration: 200,
  ...extra,
});

describe("TrackList genre column", () => {
  it("links every genre of a multi-genre track separately", async () => {
    const onnavigate = vi.fn();
    render(TrackList, { tracks: [track({ genre: "hardstyle,hardcore" })], onnavigate });

    const hardstyle = screen.getByText("hardstyle");
    const hardcore = screen.getByText("hardcore");

    await hardstyle.click();
    expect(onnavigate).toHaveBeenCalledWith("genre:hardstyle");

    await hardcore.click();
    expect(onnavigate).toHaveBeenCalledWith("genre:hardcore");
  });

  it("keeps the genres readable as one comma-separated string", () => {
    render(TrackList, { tracks: [track({ genre: "hardstyle, hardcore" })], onnavigate: vi.fn() });

    const cell = screen.getByTitle("hardstyle, hardcore");
    expect(cell.textContent.replace(/\s+/g, " ").trim()).toBe("hardstyle, hardcore");
  });

  it("still links a single genre", async () => {
    const onnavigate = vi.fn();
    render(TrackList, { tracks: [track({ genre: "techno" })], onnavigate });

    await screen.getByText("techno").click();
    expect(onnavigate).toHaveBeenCalledWith("genre:techno");
  });
});

describe("TrackList duration column", () => {
  it("shows a song's duration as m:ss", () => {
    render(TrackList, { tracks: [track({ duration: 245 })], onnavigate: vi.fn() });
    expect(screen.getByText("4:05")).toBeTruthy();
  });

  it("shows a set's duration as h:mm, not m:ss, once it crosses the ten-minute boundary", () => {
    render(TrackList, { tracks: [track({ duration: 4530 })], onnavigate: vi.fn() }); // 1h 15m 30s
    expect(screen.getByText("1:15")).toBeTruthy();
    expect(screen.queryByText("75:30")).toBeNull();
  });

  it("decides per row rather than on the mode a mixed list might not agree with", () => {
    render(TrackList, {
      tracks: [track({ id: "song", duration: 200 }), track({ id: "set", duration: 4200 })],
      onnavigate: vi.fn(),
    });
    expect(screen.getByText("3:20")).toBeTruthy();
    expect(screen.getByText("1:10")).toBeTruthy();
  });
});

describe("TrackList versions", () => {
  it("offers the versions of a song the server has grouped", () => {
    render(TrackList, { tracks: [track({ workId: 42 })], onnavigate: vi.fn() });
    expect(screen.getByTitle("Versies")).toBeTruthy();
  });

  it("offers nothing for a track the server has not grouped", () => {
    // Half the library carries no work while the worker catches up, and a button that
    // opens an empty page is worse than no button.
    render(TrackList, { tracks: [track()], onnavigate: vi.fn() });
    expect(screen.queryByTitle("Versies")).toBeNull();
  });

  it("opens the song page rather than playing the row", async () => {
    const onnavigate = vi.fn();
    render(TrackList, { tracks: [track({ workId: 42 })], onnavigate });

    await screen.getByTitle("Versies").click();

    expect(onnavigate).toHaveBeenCalledWith("song:42");
  });
});

// A tablet shows the sidebar layout, so the table is far narrower than the viewport that
// `md:`/`lg:` read: every optional column switched on and left the title ~65px wide.
describe("TrackList column layout", () => {
  it("shows optional columns by the table's own width, not the viewport's", () => {
    const { container } = render(TrackList, {
      tracks: [track({ genre: "hardcore" })],
      onnavigate: vi.fn(),
    });

    const table = container.querySelector("table");
    expect(table.parentElement.className).toContain("@container");
    const headers = [...container.querySelectorAll("thead th")].map((th) => th.className);
    expect(headers.some((c) => /\b(md|lg):table-cell/.test(c))).toBe(false);
    expect(headers.filter((c) => c.includes("@xl:table-cell")).length).toBe(1); // album
  });

  it("keeps the date on one line and truncates the album and artist cells", () => {
    render(TrackList, {
      tracks: [
        track({
          album: "Soundcloud (BÖSSELS)",
          artist: "Bössels,Revellers",
          originalDate: "2026-09-20",
        }),
      ],
      onnavigate: vi.fn(),
    });

    expect(screen.getByTitle("Soundcloud (BÖSSELS)").className).toContain("truncate");
    expect(screen.getByText("20-09-2026").className).toContain("whitespace-nowrap");
    expect(screen.getByText("Bössels,Revellers").closest(".truncate")).toBeTruthy();
  });

  it("drops the rating column on a touch device, whose stars sit under the artist", () => {
    isMobile.set(true);
    try {
      const { container } = render(TrackList, { tracks: [track()], onnavigate: vi.fn() });
      expect(container.querySelectorAll("thead th").length).toBe(
        container.querySelector("tbody tr").querySelectorAll("td").length,
      );
      const headers = [...container.querySelectorAll("thead th")].map((th) => th.className);
      expect(headers.some((c) => c.includes("@4xl:table-cell"))).toBe(false);
      expect(screen.getByTestId("mobile-rating")).toBeTruthy();
    } finally {
      isMobile.set(false);
    }
  });
});
