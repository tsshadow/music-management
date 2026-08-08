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
