import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/svelte";
import TrackList from "../../src/lib/TrackList.svelte";

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
