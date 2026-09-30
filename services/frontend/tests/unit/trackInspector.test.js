import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import TrackInspector from "../../src/lib/management/library/TrackInspector.svelte";

const TRACK = {
  id: 42,
  title: "Raise Your Fist",
  artist: "Angerfist",
  label: "Roughstate",
  bpm: 174.6,
  release_year: 2024,
  duration_secs: 245,
  genres: ["Hardcore", "Uptempo"],
  created_at: "2026-01-01T01:00:00Z",
  file_path: "/music/angerfist/raise-your-fist.mp3",
};

function props(overrides = {}) {
  return { track: TRACK, onRerunParse: vi.fn(), onRedownload: vi.fn(), ...overrides };
}

describe("TrackInspector", () => {
  it("asks for a track when nothing is selected", () => {
    render(TrackInspector, props({ track: null }));

    expect(screen.getByText("Geen track geselecteerd")).toBeTruthy();
    expect(screen.getByText("Kies een track om de details te zien.")).toBeTruthy();
  });

  it("shows the title, artist and label of the selected track", () => {
    render(TrackInspector, props());

    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
    expect(screen.getByText("Angerfist")).toBeTruthy();
    expect(screen.getByText("Roughstate")).toBeTruthy();
  });

  it("rounds the bpm to a whole number", () => {
    render(TrackInspector, props());

    expect(screen.getByText("175")).toBeTruthy();
  });

  it("marks a BPM that is not measured with ≈", () => {
    render(TrackInspector, props({ track: { ...TRACK, bpm: 151.999, bpm_approximate: 1 } }));

    expect(screen.getByText("≈152")).toBeTruthy();
  });

  it("shows the duration as minutes and padded seconds", () => {
    render(TrackInspector, props());

    expect(screen.getByText("4:05")).toBeTruthy();
  });

  it("leaves out the duration when the track has none", () => {
    render(TrackInspector, props({ track: { ...TRACK, duration_secs: 0 } }));

    expect(screen.queryByText("Duur")).toBeNull();
  });

  it("leaves out the statistics the track does not have", () => {
    render(TrackInspector, props({ track: { id: 1, title: "Untagged" } }));

    expect(screen.queryByText("BPM")).toBeNull();
    expect(screen.queryByText("Jaar")).toBeNull();
    expect(screen.queryByText("Genres")).toBeNull();
    expect(screen.getByText("ID: 1")).toBeTruthy();
  });

  it("lists every genre on the track", () => {
    render(TrackInspector, props());

    expect(screen.getByText("Hardcore")).toBeTruthy();
    expect(screen.getByText("Uptempo")).toBeTruthy();
  });

  it("leaves out the genre block when the list is empty", () => {
    render(TrackInspector, props({ track: { ...TRACK, genres: [] } }));

    expect(screen.queryByText("Genres")).toBeNull();
  });

  it("shows where the file lives", () => {
    render(TrackInspector, props());

    expect(screen.getByText("/music/angerfist/raise-your-fist.mp3")).toBeTruthy();
  });

  it("re-analyses the track that is on screen", async () => {
    const onRerunParse = vi.fn();
    render(TrackInspector, props({ onRerunParse }));

    await fireEvent.click(screen.getByText("Opnieuw analyseren"));

    expect(onRerunParse).toHaveBeenCalledWith(TRACK);
  });

  it("re-downloads the track that is on screen", async () => {
    const onRedownload = vi.fn();
    render(TrackInspector, props({ onRedownload }));

    await fireEvent.click(screen.getByText("Opnieuw downloaden"));

    expect(onRedownload).toHaveBeenCalledWith(TRACK);
  });
});
