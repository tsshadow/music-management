import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/svelte";
import { get } from "svelte/store";
import TrackList from "../../src/lib/TrackList.svelte";
import { currentTrack, playlist, isMobile, trackListLines } from "../../src/lib/store.js";

const track = {
  id: "2",
  title: "Second",
  artist: "Artist",
  artistId: "a",
  album: "Record",
  albumId: "r",
  genre: "Hardcore",
  year: 2024,
  duration: 180,
  globalPlayCount: 12,
  label: "Label",
  workId: "w",
};

/** Phone actions must never bubble into the row's play handler. */
describe("phone song details", () => {
  beforeEach(() => {
    isMobile.set(true);
    trackListLines.set(2);
    currentTrack.set({ id: "1", title: "First" });
    playlist.set([{ id: "1" }]);
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok" } }),
    }));
  });

  it("opens metadata without playback and reuses the queue action", async () => {
    render(TrackList, { tracks: [track], onnavigate: vi.fn() });
    await fireEvent.click(screen.getByLabelText("Nummerdetails"));
    const sheet = within(screen.getByTestId("song-details"));
    expect(sheet.getByText("Label")).toBeTruthy();
    expect(sheet.getByText("Hardcore")).toBeTruthy();
    expect(sheet.getByText(/12/)).toBeTruthy();
    expect(get(currentTrack).id).toBe("1");
    await fireEvent.click(sheet.getByText("Aan wachtrij toevoegen"));
    expect(get(playlist).map((item) => item.id)).toEqual(["1", "2"]);
    expect(get(currentTrack).id).toBe("1");
  });

  it("links versions and closes the sheet", async () => {
    const onnavigate = vi.fn();
    render(TrackList, { tracks: [track], onnavigate });
    await fireEvent.click(screen.getByLabelText("Nummerdetails"));
    await fireEvent.click(within(screen.getByTestId("song-details")).getByText("Versies"));
    expect(onnavigate).toHaveBeenCalledWith("song:w");
    expect(screen.queryByTestId("song-details")).toBeNull();
  });

  it.each([2, 3])("renders %i metadata lines with a working album link", async (lines) => {
    trackListLines.set(lines);
    const onnavigate = vi.fn();
    render(TrackList, { tracks: [track], onnavigate });
    const third = screen.queryByTestId("track-third-line");
    expect(Boolean(third)).toBe(lines === 3);
    if (third) {
      expect(third.textContent).toContain("2024");
      await fireEvent.click(within(third).getByRole("button", { name: "Record" }));
      expect(onnavigate).toHaveBeenCalledWith("album:r");
      expect(get(currentTrack).id).toBe("1");
    }
    expect(screen.getAllByLabelText("5 sterren")).toHaveLength(1);
  });
  it("uses the listening timestamp on the third history line", () => {
    trackListLines.set(3);
    const listenedAt = "2026-09-14T12:00:00Z";
    render(TrackList, { tracks: [{ ...track, listenedAt }], showDate: true, onnavigate: vi.fn() });
    expect(screen.getByTestId("track-third-line").textContent).toContain(
      new Date(listenedAt).toLocaleString(),
    );
  });

  it("removes the selected occurrence from a phone queue", async () => {
    const first = { ...track, id: "first" };
    const last = { ...track, id: "last" };
    playlist.set([first, track, last]);
    render(TrackList, { tracks: [first, track, last], isQueue: true, onnavigate: vi.fn() });
    await fireEvent.click(screen.getAllByLabelText("Nummerdetails")[1]);
    await fireEvent.click(within(screen.getByTestId("song-details")).getByText("Verwijderen"));
    expect(get(playlist).map((item) => item.id)).toEqual(["first", "last"]);
  });
});
