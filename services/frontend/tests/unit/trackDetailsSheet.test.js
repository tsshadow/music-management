import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/svelte";
import TrackDetailsSheet from "../../src/lib/TrackDetailsSheet.svelte";

// The sheet asks MuMa for the tags when it opens; by default MuMa has never
// seen the file, which renders no tags section at all.
vi.mock("../../src/lib/trackDetails.js", () => ({
  fetchTrackDetails: (...args) => globalThis.__fetchTrackDetails(...args),
}));

beforeEach(() => {
  globalThis.__fetchTrackDetails = vi.fn(async () => ({ state: "none", details: null }));
});

const track = (extra = {}) => ({
  id: "1",
  title: "Track",
  artist: "Artist",
  album: "Album",
  albumId: "a1",
  duration: 200,
  ...extra,
});

function renderSheet(props = {}) {
  return render(TrackDetailsSheet, {
    track: track(),
    onclose: vi.fn(),
    ...props,
  });
}

describe("TrackDetailsSheet genre chips", () => {
  it("renders one chip per genre and navigates on tap", async () => {
    const onnavigate = vi.fn();
    renderSheet({ track: track({ genre: "hardstyle,hardcore" }), onnavigate });

    await screen.getByText("hardstyle").click();
    expect(onnavigate).toHaveBeenCalledWith("genre:hardstyle");

    await screen.getByText("hardcore").click();
    expect(onnavigate).toHaveBeenCalledWith("genre:hardcore");
  });

  it("shows nothing when the track has no genre", () => {
    renderSheet({ track: track({ genre: "" }) });
    expect(screen.queryAllByTestId("genre-chip")).toHaveLength(0);
  });
});

describe("TrackDetailsSheet label chip", () => {
  it("navigates to the label", async () => {
    const onnavigate = vi.fn();
    renderSheet({ track: track({ label: "Art of Creation" }), onnavigate });

    await screen.getByText("Art of Creation").click();
    expect(onnavigate).toHaveBeenCalledWith("label:Art of Creation");
  });

  it("colours the label chip like the player does, and the genre chip not", () => {
    renderSheet({ track: track({ label: "Art of Creation", genre: "hardstyle" }) });

    const label = screen.getByTestId("label-chip");
    const genre = screen.getByTestId("genre-chip");
    expect(label.dataset.kind).toBe("label");
    expect(label.className).toContain("bg-[#3a2c16]");
    expect(genre.dataset.kind).toBe("genre");
    expect(genre.className).not.toContain("bg-[#3a2c16]");
  });

  it("falls back to publisher when there is no label", async () => {
    const onnavigate = vi.fn();
    renderSheet({ track: track({ publisher: "Scantraxx" }), onnavigate });

    await screen.getByText("Scantraxx").click();
    expect(onnavigate).toHaveBeenCalledWith("label:Scantraxx");
  });
});

describe("TrackDetailsSheet festival chip", () => {
  it("navigates to the festival when the track carries one", async () => {
    const onnavigate = vi.fn();
    renderSheet({ track: track({ festival: "Defqon.1" }), onnavigate });

    await screen.getByTestId("festival-chip").click();
    expect(onnavigate).toHaveBeenCalledWith("festival:Defqon.1");
  });

  it("renders one chip per festival from the array LMS sends", async () => {
    const onnavigate = vi.fn();
    renderSheet({ track: track({ festivals: ["Defqon.1", "Dominator"] }), onnavigate });

    const chips = screen.getAllByTestId("festival-chip");
    expect(chips.map((c) => c.textContent)).toEqual(["Defqon.1", "Dominator"]);
    await chips[1].click();
    expect(onnavigate).toHaveBeenCalledWith("festival:Dominator");
  });

  it("renders no festival chip without one", () => {
    renderSheet();
    expect(screen.queryByTestId("festival-chip")).toBeNull();
  });
});

describe("TrackDetailsSheet mood chips", () => {
  it("renders moods without a navigation target", () => {
    const onnavigate = vi.fn();
    renderSheet({ track: track({ moods: ["Euphoric", "Dark"] }), onnavigate });

    const chips = screen.getAllByTestId("mood-chip");
    expect(chips.map((c) => c.textContent)).toEqual(["Euphoric", "Dark"]);
    // Moods are plain text, not buttons -- there is no route to navigate to.
    expect(chips[0].tagName).not.toBe("BUTTON");
  });
});

describe("TrackDetailsSheet file section", () => {
  it("shows file name, format line, folder and the day it was added, no toggle", () => {
    renderSheet({
      track: track({
        bitRate: 320,
        suffix: "mp3",
        samplingRate: 44100,
        bitDepth: 0,
        channelCount: 2,
        size: 9800000,
        created: "2026-09-02T10:00:00Z",
        path: "Soundcloud/Complex/Complex - Rammeroni.mp3",
      }),
    });

    const section = screen.getByTestId("file-details");
    expect(screen.getByTestId("file-name").textContent).toBe("Complex - Rammeroni.mp3");
    expect(screen.getByTestId("file-format").textContent).toBe(
      "MP3 · 320 kbps · 44.1 kHz · stereo · 9.8 MB",
    );
    expect(section.textContent).toContain("Soundcloud/Complex");
    expect(section.textContent).toContain("02-09-2026");
    expect(screen.queryByTestId("technical-toggle")).toBeNull();
  });

  it("renders no file section when nothing about the file is known", () => {
    renderSheet({ track: track({ bitRate: null, suffix: null, path: null }) });
    expect(screen.queryByTestId("file-details")).toBeNull();
  });
});

describe("TrackDetailsSheet tags section", () => {
  it("asks MuMa by the track's path and lists what it knows", async () => {
    globalThis.__fetchTrackDetails.mockResolvedValue({
      state: "ok",
      details: {
        channels: [{ platform: "youtube", name: "Q-dance" }],
        source_url: "https://youtu.be/abc",
        source: "YOUTUBE",
        bpm: 150,
        tags: { catalognumber: ["Q404PRO"], isrc: ["NL123"] },
      },
    });
    renderSheet({ track: track({ path: "Youtube/Q-dance/a.mp3" }) });

    expect(globalThis.__fetchTrackDetails).toHaveBeenCalledWith("Youtube/Q-dance/a.mp3");
    await waitFor(() => expect(screen.getByTestId("tag-details").textContent).toContain("Q404PRO"));
    const text = screen.getByTestId("tag-details").textContent;
    expect(text).toContain("Kanaal");
    expect(text).toContain("Q-dance (Youtube)");
    expect(text).toContain("Herkomst");
    expect(text).toContain("Youtube");
    expect(text).toContain("BPM");
    expect(text).toContain("150");
    expect(text).toContain("Catalogusnummer");
    expect(text).toContain("isrc");
    expect(text).toContain("NL123");
    const link = screen.getByText("https://youtu.be/abc");
    expect(link.getAttribute("href")).toBe("https://youtu.be/abc");
  });

  it("hands the source URL to the system browser rather than navigating the WebView", async () => {
    globalThis.__fetchTrackDetails.mockResolvedValue({
      state: "ok",
      details: { source_url: "https://youtu.be/abc", tags: {} },
    });
    const platform = { system: { openUrl: vi.fn(async () => {}) } };
    renderSheet({ track: track({ path: "a.mp3" }), platform });

    await waitFor(() => screen.getByText("https://youtu.be/abc"));
    await fireEvent.click(screen.getByText("https://youtu.be/abc"));

    expect(platform.system.openUrl).toHaveBeenCalledWith("https://youtu.be/abc");
  });

  it("navigates from a curated channel row the way a chip does", async () => {
    globalThis.__fetchTrackDetails.mockResolvedValue({
      state: "ok",
      details: {
        channels: [{ platform: "youtube", name: "Q-dance", label: "Q-dance Records" }],
        tags: {},
      },
    });
    const onnavigate = vi.fn();
    renderSheet({ track: track({ path: "a.mp3" }), onnavigate });

    await waitFor(() => screen.getByTestId("tag-link"));
    await fireEvent.click(screen.getByTestId("tag-link"));

    expect(onnavigate).toHaveBeenCalledWith("label:Q-dance Records");
  });

  it("shows no tags section when MuMa has never scanned the file", async () => {
    renderSheet({ track: track({ path: "a.mp3" }) });
    await waitFor(() => expect(screen.queryByText("Tags ophalen…")).toBeNull());
    expect(screen.queryByTestId("tag-details")).toBeNull();
  });

  it("says so when MuMa could not be reached, rather than looking like a file without tags", async () => {
    globalThis.__fetchTrackDetails.mockResolvedValue({ state: "error", details: null });
    renderSheet({ track: track({ path: "a.mp3" }) });
    await waitFor(() => expect(screen.getByTestId("tags-unavailable")).toBeTruthy());
  });
});

describe("TrackDetailsSheet versions", () => {
  it("offers the song page only when the track has a workId", () => {
    renderSheet({ track: track({ workId: 42 }) });
    expect(screen.getByText("Versies")).toBeTruthy();
  });

  it("hides it without a workId", () => {
    renderSheet({ track: track({ workId: null }) });
    expect(screen.queryByText("Versies")).toBeNull();
  });
});

describe("TrackDetailsSheet artists together", () => {
  it("offers a combined search for two or more artists", async () => {
    const onnavigate = vi.fn();
    renderSheet({
      track: track({
        artists: [
          { id: "a1", name: "Headhunterz" },
          { id: "a2", name: "Wildstylez" },
        ],
      }),
      onnavigate,
    });

    await screen.getByTestId("artist-together").click();
    expect(onnavigate).toHaveBeenCalledWith("search:Headhunterz × Wildstylez");
  });

  it("says nothing for a single artist", () => {
    renderSheet({ track: track({ artistId: "a1", artist: "Headhunterz" }) });
    expect(screen.queryByTestId("artist-together")).toBeNull();
  });
});

describe("TrackDetailsSheet rating and actions", () => {
  it("rates the track with the star tapped", async () => {
    const onrate = vi.fn();
    renderSheet({ rating: 0, onrate });

    await screen.getAllByLabelText("Beoordeel met 4 sterren")[0].click();
    expect(onrate).toHaveBeenCalledWith(4);
  });

  it("calls through to the queue actions it is handed", async () => {
    const onlyrics = vi.fn();
    const onplaynext = vi.fn();
    const onaddqueue = vi.fn();
    renderSheet({ onlyrics, onplaynext, onaddqueue });

    await screen.getByText("Lyrics").click();
    await screen.getByText("Hierna afspelen").click();
    await screen.getByText("Aan wachtrij toevoegen").click();

    expect(onlyrics).toHaveBeenCalled();
    expect(onplaynext).toHaveBeenCalled();
    expect(onaddqueue).toHaveBeenCalled();
  });

  it("only offers remove when the caller hands one in", () => {
    renderSheet({ onremove: null });
    expect(screen.queryByText("Verwijderen")).toBeNull();
  });

  it("shows the lyrics row by default, for callers that never checked", () => {
    renderSheet();
    expect(screen.getByText("Lyrics")).toBeTruthy();
  });

  it("hides the lyrics row when the caller says there are none", () => {
    renderSheet({ hasLyrics: false });
    expect(screen.queryByText("Lyrics")).toBeNull();
  });

  it("navigates to the album and each artist", async () => {
    const onnavigate = vi.fn();
    renderSheet({
      track: track({ albumId: "al1", artists: [{ id: "ar1", name: "Angerfist" }] }),
      onnavigate,
    });

    await screen.getByText("Naar album").click();
    expect(onnavigate).toHaveBeenCalledWith("album:al1");

    await screen.getByText("Naar artiest: Angerfist").click();
    expect(onnavigate).toHaveBeenCalledWith("artist:ar1");
  });
});
