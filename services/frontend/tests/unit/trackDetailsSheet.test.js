import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/svelte";
import TrackDetailsSheet from "../../src/lib/TrackDetailsSheet.svelte";

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

describe("TrackDetailsSheet technical details", () => {
  it("stays collapsed until toggled, then shows format and path", async () => {
    renderSheet({ track: track({ bitRate: 320, suffix: "flac", path: "/mnt/music/a.flac" }) });

    expect(screen.queryByTestId("technical-body")).toBeNull();

    await screen.getByTestId("technical-toggle").click();

    const body = screen.getByTestId("technical-body");
    expect(body.textContent).toContain("320 kbps");
    expect(body.textContent).toContain("FLAC");
    expect(body.textContent).toContain("/mnt/music/a.flac");
  });

  it("renders no technical toggle when nothing technical is known", () => {
    renderSheet({ track: track({ bitRate: null, suffix: null, path: null }) });
    expect(screen.queryByTestId("technical-toggle")).toBeNull();
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
