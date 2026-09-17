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
    onnavigate: vi.fn(),
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

  it("reads the album as the playing-from context, under a caption", () => {
    renderNowPlaying();

    expect(screen.getByText("Afspelen vanuit")).toBeTruthy();
    expect(screen.getByText("Bad Blood")).toBeTruthy();
  });

  it("falls back to the queue when the track has no album", () => {
    renderNowPlaying({ track: { ...TRACK, album: null } });

    expect(screen.getByText("Wachtrij")).toBeTruthy();
  });

  it("renders the header without the old all-caps treatment", () => {
    renderNowPlaying();

    const name = screen.getByText("Bad Blood");
    expect(name.className).not.toMatch(/uppercase/);
    expect(name.className).toMatch(/font-bold/);
    const caption = screen.getByText("Afspelen vanuit");
    expect(caption.className).not.toMatch(/uppercase/);
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

  it("gives each star a 44px tap target", () => {
    renderNowPlaying();

    const star = screen.getAllByLabelText("4 sterren")[0];
    expect(star.className).toContain("w-11");
    expect(star.className).toContain("h-11");
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

    const cover = screen.getByTestId("now-playing-artwork");
    await fireEvent.touchStart(cover, { touches: [{ clientY: 100 }] });
    await fireEvent.touchEnd(cover, { changedTouches: [{ clientY: 220 }] });

    expect(onclose).toHaveBeenCalled();
  });

  it("does not close on a short tap on the cover", async () => {
    const onclose = vi.fn();
    renderNowPlaying({ onclose });

    const cover = screen.getByTestId("now-playing-artwork");
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

  it("opens the details sheet from the header's overflow button", async () => {
    renderNowPlaying();

    await fireEvent.click(screen.getByTestId("now-playing-details"));

    expect(screen.getByTestId("song-details")).toBeTruthy();
    expect(screen.getByLabelText("Meer")).toBeTruthy();
  });

  it("hides the sheet's lyrics row when the player found none for the track", async () => {
    renderNowPlaying({ lyricsLines: [] });

    await fireEvent.click(screen.getByTestId("now-playing-details"));

    expect(screen.queryByText("Lyrics")).toBeNull();
  });

  it("opens a sheet with the lyrics Player.svelte already fetched, from the details sheet's own row", async () => {
    renderNowPlaying({ lyricsLines: ["Raise your fist", "in the air"] });

    await fireEvent.click(screen.getByTestId("now-playing-details"));
    await fireEvent.click(screen.getByText("Lyrics"));

    expect(screen.getByText("Raise your fist")).toBeTruthy();
    expect(screen.getByText("in the air")).toBeTruthy();
  });
});

describe("NowPlaying artwork and background", () => {
  it("renders exactly one artwork slot for the track", () => {
    renderNowPlaying({ coverUrl: "https://example.test/cover.jpg" });

    const slot = screen.getByTestId("now-playing-artwork");
    const images = slot.querySelectorAll("img");
    const panels = slot.querySelectorAll('[data-testid="artwork-panel"]');
    expect(images.length + panels.length).toBe(1);
  });

  it("tints the background with the track's genre colour", () => {
    renderNowPlaying({ tint: "#ff4d00" });

    const root = screen.getByTestId("now-playing");
    expect(root).toHaveAttribute("data-tint", "#ff4d00");
    // jsdom re-serialises the hex colours it parsed out of the `style`
    // attribute as `rgb(...)`, so the assertion follows that rather than the
    // literal string this component wrote.
    expect(root.getAttribute("style")).toContain("linear-gradient");
    expect(root.getAttribute("style")).toContain("color-mix(in srgb, rgb(255, 77, 0) 55%");
  });

  it("keeps the plain dark background without a tint", () => {
    renderNowPlaying({ tint: null });

    const root = screen.getByTestId("now-playing");
    expect(root).not.toHaveAttribute("data-tint");
    expect(root.getAttribute("style")).toContain("background-color: rgb(18, 18, 18)");
    expect(root.getAttribute("style")).not.toContain("linear-gradient");
  });
});

describe("NowPlaying track info", () => {
  it("shows every artist through ArtistList and navigates to one that has an id", async () => {
    const onclose = vi.fn();
    const onnavigate = vi.fn();
    renderNowPlaying({
      track: { ...TRACK, artists: [{ id: "ar1", name: "Angerfist" }] },
      onclose,
      onnavigate,
    });

    await fireEvent.click(screen.getByText("Angerfist"));

    // Now Playing closes itself before handing the tap on to the router --
    // otherwise the full-screen player would be left stranded over the
    // artist page it just opened.
    expect(onclose).toHaveBeenCalled();
    expect(onnavigate).toHaveBeenCalledWith("artist:ar1");
  });

  it("makes the album line a link to the album, and closes first", async () => {
    const onclose = vi.fn();
    const onnavigate = vi.fn();
    renderNowPlaying({ track: { ...TRACK, albumId: "al1" }, onclose, onnavigate });

    await fireEvent.click(screen.getByText("Bad Blood"));

    expect(onclose).toHaveBeenCalled();
    expect(onnavigate).toHaveBeenCalledWith("album:al1");
  });

  it("does not make the album line a link without an album id", () => {
    renderNowPlaying({ track: { ...TRACK, albumId: null } });

    const name = screen.getByText("Bad Blood");
    expect(name.closest("button")).toBeNull();
  });

  it("shows every genre as its own chip button and navigates through one", async () => {
    const onclose = vi.fn();
    const onnavigate = vi.fn();
    renderNowPlaying({ track: { ...TRACK, genre: "hardstyle,hardcore" }, onclose, onnavigate });

    expect(screen.getByTestId("now-playing-meta")).toBeTruthy();
    const hardstyle = screen.getByText("hardstyle");
    const hardcore = screen.getByText("hardcore");
    expect(hardstyle.tagName).toBe("BUTTON");
    expect(hardcore.tagName).toBe("BUTTON");

    await fireEvent.click(hardstyle);

    expect(onclose).toHaveBeenCalled();
    expect(onnavigate).toHaveBeenCalledWith("genre:hardstyle");
  });

  it("shows no meta line for a track with no genre, date or label", () => {
    renderNowPlaying({ track: TRACK });
    expect(screen.queryByTestId("now-playing-meta")).toBeNull();
  });

  it("does not put the release date among the meta chips", () => {
    // A date with no genre and no label used to still show as the sole meta
    // item; now the row does not render at all for it, since the date moved
    // to the details sheet.
    renderNowPlaying({ track: { ...TRACK, originalDate: "2026-01-05" } });

    expect(screen.queryByTestId("now-playing-meta")).toBeNull();
    expect(screen.queryByText("05-01-2026")).toBeNull();
  });

  it("offers the song page only when the track has a workId", () => {
    renderNowPlaying({ track: { ...TRACK, workId: 42 } });
    expect(screen.getByTestId("now-playing-song")).toBeTruthy();
  });

  it("hides the song button without a workId", () => {
    renderNowPlaying({ track: { ...TRACK, workId: null } });
    expect(screen.queryByTestId("now-playing-song")).toBeNull();
  });

  it("navigates to the song page and closes first", async () => {
    const onclose = vi.fn();
    const onnavigate = vi.fn();
    renderNowPlaying({ track: { ...TRACK, workId: 42 }, onclose, onnavigate });

    await fireEvent.click(screen.getByTestId("now-playing-song"));

    expect(onclose).toHaveBeenCalled();
    expect(onnavigate).toHaveBeenCalledWith("song:42");
  });

  it("opens the details sheet for the current track", async () => {
    renderNowPlaying({ track: { ...TRACK, genre: "hardstyle" } });

    await fireEvent.click(screen.getByTestId("now-playing-details"));

    expect(screen.getByTestId("song-details")).toBeTruthy();
    expect(screen.getAllByText("Raise Your Fist").length).toBeGreaterThan(0);
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
