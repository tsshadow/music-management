import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import NowPlaying from "../../src/lib/NowPlaying.svelte";

const TRACK = {
  id: "song-1",
  title: "Raise Your Fist",
  artist: "Angerfist",
  album: "Bad Blood",
};

function renderNowPlaying(props = {}) {
  return render(NowPlaying, {
    open: true,
    track: TRACK,
    playing: false,
    progress: 30,
    duration: 240,
    rating: 0,
    onclose: vi.fn(),
    ontogglePlay: vi.fn(),
    onnext: vi.fn(),
    onprev: vi.fn(),
    onrate: vi.fn(),
    ontoggleShuffle: vi.fn(),
    ontoggleRepeat: vi.fn(),
    onseek: vi.fn(),
    ontoggleEqualizer: vi.fn(),
    ontoggleQueue: vi.fn(),
    ...props,
  });
}

describe("NowPlaying", () => {
  it("renders nothing when closed", () => {
    renderNowPlaying({ open: false });

    expect(screen.queryByTestId("now-playing")).toBeNull();
  });

  it("shows the track's title, artist and cover", () => {
    renderNowPlaying({ coverUrl: "https://example.test/cover.jpg" });

    expect(screen.getByTestId("now-playing")).toBeTruthy();
    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
    expect(screen.getByText("Angerfist")).toBeTruthy();
    expect(screen.getByAltText("Raise Your Fist")).toHaveAttribute(
      "src",
      "https://example.test/cover.jpg",
    );
  });

  it("reads the album as the playing-from context", () => {
    renderNowPlaying();

    expect(screen.getByText("Afspelen uit: Bad Blood")).toBeTruthy();
  });

  it("falls back to the queue when the track has no album", () => {
    renderNowPlaying({ track: { ...TRACK, album: null } });

    expect(screen.getByText("Afspelen uit: Wachtrij")).toBeTruthy();
  });

  it("calls back to the player for play/pause", async () => {
    const ontogglePlay = vi.fn();
    renderNowPlaying({ ontogglePlay });

    await fireEvent.click(screen.getByLabelText("Afspelen"));

    expect(ontogglePlay).toHaveBeenCalled();
  });

  it("labels the button for pause once playing", () => {
    renderNowPlaying({ playing: true });

    expect(screen.getByLabelText("Pauze")).toBeTruthy();
  });

  it("calls back for next and previous", async () => {
    const onnext = vi.fn();
    const onprev = vi.fn();
    renderNowPlaying({ onnext, onprev });

    await fireEvent.click(screen.getByLabelText("Volgende"));
    await fireEvent.click(screen.getByLabelText("Vorige"));

    expect(onnext).toHaveBeenCalled();
    expect(onprev).toHaveBeenCalled();
  });

  it("rates the track with the star tapped", async () => {
    const onrate = vi.fn();
    renderNowPlaying({ onrate });

    await fireEvent.click(screen.getAllByLabelText("4 sterren")[0]);

    expect(onrate).toHaveBeenCalledWith(4);
  });

  it("toggles shuffle and repeat", async () => {
    const ontoggleShuffle = vi.fn();
    const ontoggleRepeat = vi.fn();
    renderNowPlaying({ ontoggleShuffle, ontoggleRepeat });

    await fireEvent.click(screen.getByLabelText("Shuffle"));
    await fireEvent.click(screen.getByLabelText("Herhalen"));

    expect(ontoggleShuffle).toHaveBeenCalled();
    expect(ontoggleRepeat).toHaveBeenCalled();
  });

  it("opens the equalizer and the queue from its bottom row", async () => {
    const ontoggleEqualizer = vi.fn();
    const ontoggleQueue = vi.fn();
    renderNowPlaying({ ontoggleEqualizer, ontoggleQueue, equalizerSupported: true });

    await fireEvent.click(screen.getByLabelText("Equalizer"));
    await fireEvent.click(screen.getByLabelText("Wachtrij"));

    expect(ontoggleEqualizer).toHaveBeenCalled();
    expect(ontoggleQueue).toHaveBeenCalled();
  });

  it("hides the equalizer button when the platform has no equalizer", () => {
    renderNowPlaying({ equalizerSupported: false });

    expect(screen.queryByLabelText("Equalizer")).toBeNull();
  });

  it("closes on the chevron", async () => {
    const onclose = vi.fn();
    renderNowPlaying({ onclose });

    await fireEvent.click(screen.getByLabelText("Sluiten"));

    expect(onclose).toHaveBeenCalled();
  });

  it("closes on a firm downward drag on the cover", async () => {
    const onclose = vi.fn();
    renderNowPlaying({ onclose });

    const cover = screen.getByAltText("Raise Your Fist").parentElement;
    await fireEvent.touchStart(cover, { touches: [{ clientY: 100 }] });
    await fireEvent.touchEnd(cover, { changedTouches: [{ clientY: 220 }] });

    expect(onclose).toHaveBeenCalled();
  });

  it("does not close on a short tap on the cover", async () => {
    const onclose = vi.fn();
    renderNowPlaying({ onclose });

    const cover = screen.getByAltText("Raise Your Fist").parentElement;
    await fireEvent.touchStart(cover, { touches: [{ clientY: 100 }] });
    await fireEvent.touchEnd(cover, { changedTouches: [{ clientY: 110 }] });

    expect(onclose).not.toHaveBeenCalled();
  });

  it("seeks through the onseek callback", async () => {
    const onseek = vi.fn();
    renderNowPlaying({ onseek });

    await fireEvent.click(screen.getByLabelText("Door nummer spoelen"));

    expect(onseek).toHaveBeenCalled();
  });

  it("shows elapsed and total time", () => {
    renderNowPlaying({ progress: 65, duration: 240 });

    expect(screen.getByText("1:05")).toBeTruthy();
    expect(screen.getByText("4:00")).toBeTruthy();
  });

  it("has no lyrics button when the player found none for the track", () => {
    renderNowPlaying({ lyricsLines: [] });

    expect(screen.queryByLabelText("Lyrics")).toBeNull();
  });

  it("opens a sheet with the lyrics Player.svelte already fetched", async () => {
    renderNowPlaying({ lyricsLines: ["Raise your fist", "in the air"] });

    await fireEvent.click(screen.getByLabelText("Lyrics"));

    expect(screen.getByText("Raise your fist")).toBeTruthy();
    expect(screen.getByText("in the air")).toBeTruthy();
  });
});

describe("NowPlaying in sets mode", () => {
  it("shows h:mm:ss instead of m:ss", () => {
    renderNowPlaying({ isSetMode: true, progress: 632, duration: 7825 });

    expect(screen.getByText("0:10:32")).toBeTruthy();
    expect(screen.getByText("2:10:25")).toBeTruthy();
    expect(screen.queryByText("10:32")).toBeNull();
  });

  it("does not show ±30 s buttons for a song", () => {
    renderNowPlaying({ isSetMode: false });

    expect(screen.queryByLabelText("30 seconden terug")).toBeNull();
    expect(screen.queryByLabelText("30 seconden verder")).toBeNull();
  });

  it("skips back and forward through onskip", async () => {
    const onskip = vi.fn();
    renderNowPlaying({ isSetMode: true, onskip });

    await fireEvent.click(screen.getByLabelText("30 seconden terug"));
    await fireEvent.click(screen.getByLabelText("30 seconden verder"));

    expect(onskip).toHaveBeenCalledWith(-30);
    expect(onskip).toHaveBeenCalledWith(30);
  });

  it("scrubs through onseekTo rather than the songs-mode onseek", async () => {
    const onseekTo = vi.fn();
    const onseek = vi.fn();
    renderNowPlaying({ isSetMode: true, duration: 7200, progress: 100, onseekTo, onseek });

    const bar = screen.getByLabelText("Door nummer spoelen");
    await fireEvent.input(bar, { target: { value: "500" } });

    expect(onseekTo).toHaveBeenCalledWith(500);
    expect(onseek).not.toHaveBeenCalled();
  });

  it("overrides the scrub bar's arrow keys to skip ±30 s", async () => {
    const onskip = vi.fn();
    renderNowPlaying({ isSetMode: true, onskip });

    const bar = screen.getByLabelText("Door nummer spoelen");
    await fireEvent.keyDown(bar, { key: "ArrowRight" });
    await fireEvent.keyDown(bar, { key: "ArrowLeft" });

    expect(onskip).toHaveBeenCalledWith(30);
    expect(onskip).toHaveBeenCalledWith(-30);
  });
});
