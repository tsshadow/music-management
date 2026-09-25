import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import NowPlaying from "../../src/lib/NowPlaying.svelte";
import { queueSource, playlist, currentTrack } from "../../src/lib/store.js";

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
    expect(screen.getByTestId("now-playing-context").textContent).toBe("Bad Blood");
  });

  it("falls back to the queue when the track has no album", () => {
    renderNowPlaying({ track: { ...TRACK, album: null } });

    expect(screen.getByText("Wachtrij")).toBeTruthy();
  });

  it("renders the header without the old all-caps treatment", () => {
    renderNowPlaying();

    const name = screen.getByTestId("now-playing-context");
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

  it("centres the rating row and spreads the stars evenly, like the transport", () => {
    renderNowPlaying();

    const row = screen.getByTestId("now-playing-rating");
    expect(row.className).toContain("mx-auto");
    expect(row.className).toContain("justify-between");
    expect(row.className).toContain("max-w-xs");
    // The old left-edge alignment must not come back alongside the centring.
    expect(row.className).not.toContain("-ml-2.5");
    expect(row.querySelectorAll("button")).toHaveLength(5);
  });

  it("draws unset stars as grey outlines, not as a faded disabled glyph", () => {
    renderNowPlaying({ rating: 3 });

    const set = screen.getAllByLabelText("3 sterren")[0];
    const unset = screen.getAllByLabelText("4 sterren")[0];
    expect(set.dataset.filled).toBe("true");
    expect(set.className).toContain("text-brand");
    expect(set.querySelector("svg").getAttribute("fill")).toBe("currentColor");
    expect(unset.dataset.filled).toBe("false");
    expect(unset.className).toContain("text-muma-spotify-text");
    expect(unset.className).not.toContain("text-white/10");
    expect(unset.querySelector("svg").getAttribute("fill")).toBe("none");
    expect(unset.disabled).toBe(false);
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

  // Increment H: the output label, native only -- a null route (every browser) renders nothing.
  it("names the audio output and opens the picker from it", async () => {
    const onopenOutputPicker = vi.fn();
    renderNowPlaying({
      outputRoute: { name: "Bose QC35 II", type: "bluetooth" },
      onopenOutputPicker,
    });

    const label = screen.getByLabelText("Kies audio-uitvoer");
    expect(label.textContent).toContain("Bose QC35 II");
    expect(label.className).toContain("text-brand");

    await fireEvent.click(label);

    expect(onopenOutputPicker).toHaveBeenCalledTimes(1);
  });

  it("shows no output label without a route", () => {
    renderNowPlaying({ outputRoute: null });

    expect(screen.queryByTestId("now-playing-output")).toBeNull();
    expect(screen.queryByLabelText("Kies audio-uitvoer")).toBeNull();
  });

  it("picks a glyph per output type and falls back to the speaker's for an unknown one", () => {
    const pathFor = (type) => {
      const { unmount } = renderNowPlaying({ outputRoute: { name: "x", type } });
      const d = screen.getByTestId("now-playing-output").querySelector("path").getAttribute("d");
      unmount();
      return d;
    };

    expect(pathFor("bluetooth")).not.toBe(pathFor("speaker"));
    expect(pathFor("wired")).toBe(pathFor("usb"));
    expect(pathFor("other")).toBe(pathFor("speaker"));
    expect(pathFor("hdmi")).toBe(pathFor("speaker"));
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

  it("opens the same details sheet from the title", async () => {
    renderNowPlaying();

    await fireEvent.click(screen.getByTestId("now-playing-title"));

    expect(screen.getByTestId("song-details")).toBeTruthy();
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

    await fireEvent.click(screen.getByTestId("now-playing-album"));

    expect(onclose).toHaveBeenCalled();
    expect(onnavigate).toHaveBeenCalledWith("album:al1");
  });

  it("does not make the album line a link without an album id", () => {
    renderNowPlaying({ track: { ...TRACK, albumId: null } });

    const line = screen.getByTestId("now-playing-album-line");
    expect(line.textContent).toContain("Bad Blood");
    expect(screen.queryByTestId("now-playing-album")).toBeNull();
  });

  it("keeps the album under the artist even when the header names another place", () => {
    // The header reads the queue's source (a genre, a sort, a playlist); the album
    // is its own line so it is on the screen no matter where the queue came from.
    queueSource.set({ view: "genre:Hardstyle", name: null });
    renderNowPlaying({ track: { ...TRACK, albumId: "al1" } });

    expect(screen.getByTestId("now-playing-context").textContent).toBe("Hardstyle");
    expect(screen.getByTestId("now-playing-album").textContent).toBe("Bad Blood");
    queueSource.set(null);
  });

  it("puts the release date on the album line, right-aligned, with no separator", () => {
    renderNowPlaying({ track: { ...TRACK, originalDate: "2026-09-10" } });

    const date = screen.getByTestId("now-playing-date");
    expect(date.textContent).toBe("10-09-2026");
    // `ml-auto` pushes it to the right edge; the album truncates before it does.
    expect(date.className).toContain("ml-auto");
    expect(date.className).toContain("shrink-0");
    expect(screen.getByTestId("now-playing-album-line").textContent).not.toContain("·");
  });

  it("shows only the date when the track has no album", () => {
    renderNowPlaying({ track: { ...TRACK, album: null, year: 2024 } });

    expect(screen.getByTestId("now-playing-date").textContent).toBe("2024");
    expect(screen.queryByTestId("now-playing-album")).toBeNull();
  });

  it("renders no album line when there is neither album nor date", () => {
    renderNowPlaying({ track: { ...TRACK, album: null } });
    expect(screen.queryByTestId("now-playing-album-line")).toBeNull();
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

  it("keeps genre and label chips on one row that scrolls sideways", () => {
    renderNowPlaying({
      track: {
        ...TRACK,
        genre: "hardstyle,hardcore,uptempo,terror",
        labels: ["Masters of Hardcore"],
      },
    });

    // Every extra chip row used to push the transport further down, off the screen.
    const row = screen.getByTestId("now-playing-meta");
    expect(row.className).toContain("flex-nowrap");
    expect(row.className).toContain("overflow-x-auto");
    expect(row.className).not.toContain("flex-wrap");
    expect(screen.getByText("terror").className).toContain("shrink-0");
  });

  it("waits for a close that returns a promise before navigating", async () => {
    // `closeNowPlaying` consumes the history entry the player pushed; its `popstate`
    // arrives later. Navigating before it lands let that `popstate` restore the page
    // underneath, which is how a tap on a genre chip used to go nowhere.
    let finishClose;
    const onclose = vi.fn(() => new Promise((resolve) => (finishClose = resolve)));
    const onnavigate = vi.fn();
    renderNowPlaying({
      track: { ...TRACK, genre: "hardstyle", labels: ["Q-dance"] },
      onclose,
      onnavigate,
    });

    await fireEvent.click(screen.getByText("Q-dance"));

    expect(onclose).toHaveBeenCalled();
    expect(onnavigate).not.toHaveBeenCalled();

    finishClose();
    await waitFor(() => expect(onnavigate).toHaveBeenCalledWith("label:Q-dance"));
  });

  it("builds the screen as a one-screen stage with the transport inside it", () => {
    renderNowPlaying({ track: { ...TRACK, genre: "a,b,c,d,e,f" } });

    // The stage is at least a screen tall and the artwork box is the only part that
    // gives way, so the transport is always on the first screen.
    const stage = screen.getByTestId("now-playing-stage");
    expect(stage.className).toContain("min-h-full");
    expect(stage.contains(screen.getByTestId("now-playing-transport"))).toBe(true);
    const artwork = screen.getByTestId("now-playing-artwork");
    expect(artwork.className).toContain("flex-1");
    expect(artwork.className).toContain("min-h-0");
    // Landscape (a tablet on its side) splits cover and controls into two columns.
    expect(stage.className).toContain("landscape:grid-cols-2");
  });

  it("shows every label from the array LMS sends as its own chip", async () => {
    // `labels` is the PUBLISHER cluster on a Subsonic song node; `label` and
    // `publisher` are set by nothing, and reading only those left the player
    // without a label chip for every track while the sheet showed it fine.
    const onnavigate = vi.fn();
    renderNowPlaying({ track: { ...TRACK, labels: ["QDance", "Q-dance Records"] }, onnavigate });

    const meta = screen.getByTestId("now-playing-meta");
    expect(meta.textContent).toContain("QDance");
    expect(meta.textContent).toContain("Q-dance Records");
    await fireEvent.click(screen.getByText("QDance"));
    expect(onnavigate).toHaveBeenCalledWith("label:QDance");
  });

  it("still reads a single label field for a track that only has that", () => {
    renderNowPlaying({ track: { ...TRACK, label: "Scantraxx" } });
    expect(screen.getByTestId("now-playing-meta").textContent).toContain("Scantraxx");
  });

  it("shows no meta line for a track with no genre, date or label", () => {
    renderNowPlaying({ track: TRACK });
    expect(screen.queryByTestId("now-playing-meta")).toBeNull();
  });

  it("does not put the release date among the meta chips", () => {
    // A date with no genre and no label used to still show as the sole meta
    // item; the chip row does not render for it -- the date has its own place
    // on the album line.
    renderNowPlaying({ track: { ...TRACK, originalDate: "2026-01-05" } });

    expect(screen.queryByTestId("now-playing-meta")).toBeNull();
    expect(screen.getByTestId("now-playing-date").textContent).toBe("05-01-2026");
  });

  it("colours the label chip apart from the genre chips, by kind not by position", () => {
    // Found by text, not by index: the colour has to follow what a chip names, wherever
    // in the row it lands.
    renderNowPlaying({ track: { ...TRACK, genre: "Hardstyle; Techno", labels: ["Scantraxx"] } });

    const row = screen.getByTestId("now-playing-meta");
    const label = [...row.children].find((chip) => chip.textContent === "Scantraxx");
    const genres = [...row.children].filter((chip) => chip.textContent !== "Scantraxx");
    expect(label.dataset.kind).toBe("label");
    expect(label.className).toContain("bg-[#3a2c16]");
    expect(genres.length).toBeGreaterThan(0);
    for (const genre of genres) {
      expect(genre.dataset.kind).toBe("genre");
      expect(genre.className).not.toContain("bg-[#3a2c16]");
      expect(genre.className).toContain("bg-muma-spotify-light");
    }
  });

  it("shows a radio button only when the player wires one, tinted while a channel plays", async () => {
    renderNowPlaying();
    expect(screen.queryByTestId("now-playing-radio")).toBeNull();

    const ontoggleRadio = vi.fn();
    renderNowPlaying({ ontoggleRadio, radioActive: true });
    const button = screen.getByTestId("now-playing-radio");
    expect(button.getAttribute("aria-pressed")).toBe("true");
    expect(button.className).toContain("b266ff");
    await fireEvent.click(button);
    expect(ontoggleRadio).toHaveBeenCalled();
  });

  it("shows a news button only when the player wires one, tinted while a bulletin plays", async () => {
    renderNowPlaying();
    expect(screen.queryByTestId("now-playing-news")).toBeNull();

    const ontoggleNews = vi.fn();
    renderNowPlaying({ ontoggleNews, newsActive: true });
    const button = screen.getByTestId("now-playing-news");
    expect(button.getAttribute("aria-label")).toBe("Nieuws van het uur");
    expect(button.getAttribute("aria-pressed")).toBe("true");
    expect(button.className).toContain("b266ff");
    await fireEvent.click(button);
    expect(ontoggleNews).toHaveBeenCalled();
  });

  it("leaves the news button grey and unpressed while no bulletin plays", () => {
    renderNowPlaying({ ontoggleNews: vi.fn(), newsActive: false });

    const button = screen.getByTestId("now-playing-news");
    expect(button.getAttribute("aria-pressed")).toBe("false");
    expect(button.className).toContain("text-muma-spotify-text");
    expect(button.className).not.toContain("b266ff");
  });

  it("offers the channel choice as a bottom sheet and starts the tapped channel", async () => {
    const onstartRadio = vi.fn();
    const channels = [
      { slug: "hard", name: "Hard", filter: {} },
      { slug: "soft", name: "Soft", filter: {} },
    ];
    renderNowPlaying({
      ontoggleRadio: vi.fn(),
      onstartRadio,
      radioChannels: channels,
      showRadioPicker: true,
    });

    const picker = screen.getByTestId("now-playing-radio-picker");
    expect(picker.textContent).toContain("Hard");
    await fireEvent.click(screen.getByText("Soft"));
    expect(onstartRadio).toHaveBeenCalledWith(channels[1]);
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

// E: the header names the queue's own source rather than always the track's album.
describe("NowPlaying queue source", () => {
  beforeEach(() => {
    queueSource.set(null);
  });

  afterEach(() => {
    queueSource.set(null);
  });

  it("shows the queue source's own name over the track's album", () => {
    queueSource.set({ view: "playlist:pl1", name: "Thunderdome Essentials" });

    renderNowPlaying();

    const caption = screen.getByText("Afspelen vanuit");
    expect(caption.nextElementSibling.textContent).toBe("Thunderdome Essentials");
    expect(screen.getByTestId("now-playing-context").textContent).not.toBe("Bad Blood");
  });

  it("names an argument-based place from its view when no name was given", () => {
    queueSource.set({ view: "genre:Hardcore", name: null });

    renderNowPlaying();

    expect(screen.getByText("Hardcore")).toBeTruthy();
  });

  it("names a whole view (no name, no argument) through viewLabel", () => {
    queueSource.set({ view: "starred", name: null });

    renderNowPlaying();

    expect(screen.getByText("Favorieten")).toBeTruthy();
  });

  it("falls back to the track's album when the source names nothing printable", () => {
    queueSource.set({ view: "voice", name: null });

    renderNowPlaying();

    expect(screen.getByTestId("now-playing-context").textContent).toBe("Bad Blood");
  });

  it("prefers navigating to the queue source's place over the track's album", async () => {
    const onclose = vi.fn();
    const onnavigate = vi.fn();
    queueSource.set({ view: "genre:Hardcore", name: "Hardcore" });

    renderNowPlaying({ track: { ...TRACK, albumId: "al1" }, onclose, onnavigate });
    await fireEvent.click(screen.getByText("Hardcore"));

    expect(onclose).toHaveBeenCalled();
    expect(onnavigate).toHaveBeenCalledWith("genre:Hardcore");
  });
});

// A track with no cover shows its title twice -- once as the row's real title, once inside
// `Artwork`'s tinted fallback panel (see `TrackRowCompact.svelte`'s own tests) -- so the
// genuine title line is always the last match for a title that appears only once elsewhere.
function titleText(text) {
  return screen.getAllByText(text).pop();
}

// F: "next up" -- a preview of the queue after the currently playing position, built from
// `Player.svelte`'s `queueIndex` prop rather than a lookup, so a repeated id in the queue does
// not confuse it.
describe("NowPlaying next up", () => {
  beforeEach(() => {
    playlist.set([]);
    currentTrack.set(null);
  });

  afterEach(() => {
    playlist.set([]);
    currentTrack.set(null);
  });

  it("shows the three entries after queueIndex by position, even when an id repeats in the queue", () => {
    playlist.set([
      { id: "song-1", title: "First", artist: "Angerfist" },
      { id: "song-2", title: "Second", artist: "Angerfist" },
      { id: "song-1", title: "First Again", artist: "Angerfist" },
      { id: "song-3", title: "Third", artist: "Angerfist" },
      { id: "song-4", title: "Fourth", artist: "Angerfist" },
    ]);

    renderNowPlaying({ queueIndex: 0 });

    expect(screen.getByText("Hierna")).toBeTruthy();
    expect(titleText("Second")).toBeTruthy();
    expect(titleText("First Again")).toBeTruthy();
    expect(titleText("Third")).toBeTruthy();
    expect(screen.queryByText("Fourth")).toBeNull();
  });

  it("hides the section when nothing follows and repeat is not set to all", () => {
    playlist.set([
      { id: "1", title: "One", artist: "A" },
      { id: "2", title: "Two", artist: "A" },
      { id: "3", title: "Three", artist: "A" },
    ]);

    renderNowPlaying({ queueIndex: 2, repeatMode: "none" });

    expect(screen.queryByText("Hierna")).toBeNull();
  });

  it("wraps to the start of the queue when repeat is set to all", () => {
    playlist.set([
      { id: "1", title: "Alpha", artist: "A" },
      { id: "2", title: "Bravo", artist: "A" },
      { id: "3", title: "Charlie", artist: "A" },
      { id: "4", title: "Delta", artist: "A" },
    ]);

    renderNowPlaying({ queueIndex: 3, repeatMode: "all" });

    expect(titleText("Alpha")).toBeTruthy();
    expect(titleText("Bravo")).toBeTruthy();
    expect(titleText("Charlie")).toBeTruthy();
  });

  it("shows the shuffle line instead of a preview, and hides it once shuffle is off with nothing to preview", () => {
    playlist.set([
      { id: "1", title: "One", artist: "A" },
      { id: "2", title: "Two", artist: "A" },
    ]);

    renderNowPlaying({ queueIndex: 0, shuffleMode: true });

    expect(screen.getByText("Hierna")).toBeTruthy();
    expect(screen.getByText(/Shuffle staat aan/)).toBeTruthy();
    expect(screen.queryByText("Two")).toBeNull();
  });

  it("jumps within the queue on tap, without replacing the playlist", async () => {
    const queue = [
      { id: "1", title: "One", artist: "A" },
      { id: "2", title: "Two", artist: "A" },
    ];
    playlist.set(queue);
    currentTrack.set(queue[0]);

    renderNowPlaying({ track: queue[0], queueIndex: 0 });

    await fireEvent.click(titleText("Two"));

    expect(get(currentTrack)?.id).toBe("2");
    expect(get(playlist)).toEqual(queue);
  });
});

// F: "more from artist" -- fetched lazily, once per artist, excluding the track playing now.
describe("NowPlaying more from artist", () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  const artistTrack = { ...TRACK, artistId: "artist-1" };

  const props = (overrides = {}) => ({
    open: true,
    track: artistTrack,
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
    ...overrides,
  });

  it("fetches once per artistId and excludes the currently playing track", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": {
          status: "ok",
          tracks: {
            track: [
              { id: artistTrack.id, title: artistTrack.title, artist: artistTrack.artist },
              { id: "song-2", title: "Second", artist: artistTrack.artist },
              { id: "song-3", title: "Third", artist: artistTrack.artist },
            ],
          },
        },
      }),
    }));

    const { rerender } = render(NowPlaying, props());

    await waitFor(() => expect(titleText("Second")).toBeTruthy());
    // Two rows, not three: the fetch answered with the currently playing track too, and it
    // was filtered out of the "more from" list rather than shown among its own alternatives.
    expect(screen.getAllByTestId("track-row-compact")).toHaveLength(2);
    expect(titleText("Third")).toBeTruthy();
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);

    // Re-rendering with the same artistId (a queue position change, a rating, ...) must not
    // ask the server again.
    await rerender(props({ queueIndex: 4 }));
    expect(globalThis.fetch).toHaveBeenCalledTimes(1);
  });
});

// F: "other versions" -- only for a track with a workId, via the shared `loadVersions`.
describe("NowPlaying other versions", () => {
  it("hides the section without a workId", () => {
    renderNowPlaying({ track: { ...TRACK, workId: null } });

    expect(screen.queryByText("Versies")).toBeNull();
  });
});

// F: queue actions insert by position, not by searching for the id, so a repeated id in the
// queue does not land the "play next" insert on the wrong copy of the track.
describe("NowPlaying addAfterCurrent", () => {
  afterEach(() => {
    playlist.set([]);
  });

  it("inserts right after queueIndex even when the track's id repeats elsewhere in the queue", async () => {
    playlist.set([
      { id: "song-1", title: "First copy", artist: "Angerfist" },
      { id: "song-1", title: "Second copy", artist: "Angerfist" },
      { id: "song-2", title: "Other", artist: "Angerfist" },
    ]);

    renderNowPlaying({ queueIndex: 1 });

    await fireEvent.click(screen.getByTestId("now-playing-details"));
    await fireEvent.click(screen.getByText("Hierna afspelen"));

    expect(get(playlist).map((t) => t.title)).toEqual([
      "First copy",
      "Second copy",
      "Raise Your Fist",
      "Other",
    ]);
  });

  it("appends when there is no queue position to insert after", async () => {
    playlist.set([{ id: "song-2", title: "Other", artist: "Angerfist" }]);

    renderNowPlaying({ queueIndex: -1 });

    await fireEvent.click(screen.getByTestId("now-playing-details"));
    await fireEvent.click(screen.getByText("Hierna afspelen"));

    expect(get(playlist).map((t) => t.title)).toEqual(["Other", "Raise Your Fist"]);
  });
});

// F: the sections made the screen scroll, so the swipe-to-close gesture on the artwork must
// yield to an ordinary scroll rather than closing the player underneath it.
describe("NowPlaying swipe-to-close and scrolling", () => {
  it("ignores the gesture once the sheet has been scrolled away from the top", async () => {
    const onclose = vi.fn();
    renderNowPlaying({ onclose });

    const cover = screen.getByTestId("now-playing-artwork");
    // The stage sits between the cover and the element that actually scrolls.
    const scrollContainer = screen.getByTestId("now-playing-stage").parentElement;
    expect(scrollContainer.className).toContain("overflow-y-auto");
    Object.defineProperty(scrollContainer, "scrollTop", { value: 50, configurable: true });

    await fireEvent.touchStart(cover, { touches: [{ clientY: 100 }] });
    await fireEvent.touchEnd(cover, { changedTouches: [{ clientY: 220 }] });

    expect(onclose).not.toHaveBeenCalled();
  });
});
