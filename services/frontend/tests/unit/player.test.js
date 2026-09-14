import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import Player from "../../src/lib/Player.svelte";
import {
  credentials,
  currentTrack,
  isMobile,
  nowPlayingOpen,
  playerState,
  playlist,
  radioChannel,
  syncMode,
} from "../../src/lib/store.js";
import { notify, dismissAll } from "../../src/lib/notifications.js";

const FIRST = {
  id: "song-1",
  title: "Raise Your Fist",
  artist: "Angerfist",
  artistId: "artist-1",
  albumId: "album-1",
  duration: 240,
};
const SECOND = {
  id: "song-2",
  title: "Encore",
  artist: "Angerfist",
  artistId: "artist-1",
  albumId: "album-1",
  duration: 200,
};

function api() {
  return vi.fn(async () => ({
    ok: true,
    json: async () => ({ "subsonic-response": { status: "ok" } }),
  }));
}

function renderPlayer(props = {}) {
  return render(Player, { onnavigate: vi.fn(), ontoggleQueue: vi.fn(), ...props });
}

// Lets the click's fetch resolve and Svelte flush the resulting render, so an
// assertion sees the state the component settled on and not the one it passed
// through on the way there.
async function settled() {
  await waitFor(() =>
    expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/rest/setRating"))).toBe(true),
  );
  for (let i = 0; i < 3; i++) await new Promise((resolve) => setTimeout(resolve, 0));
}

describe("Player", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    playlist.set([FIRST, SECOND]);
    currentTrack.set(FIRST);
    playerState.set({ playing: false, repeat: "none", shuffle: false, volume: 50 });
    syncMode.set("off");
    radioChannel.set(null);
    isMobile.set(false);
    nowPlayingOpen.set(false);
    globalThis.fetch = api();
    // jsdom has no real audio pipeline.
    window.HTMLMediaElement.prototype.play = vi.fn(async () => {});
    window.HTMLMediaElement.prototype.pause = vi.fn();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    // The store outlives a render, so a notification raised here would show
    // up in the next test's assertions.
    dismissAll();
  });

  it("shows the track that is playing", () => {
    renderPlayer();

    expect(screen.getAllByText("Raise Your Fist").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Angerfist").length).toBeGreaterThan(0);
  });

  it("nothing is shown without a track", () => {
    currentTrack.set(null);

    renderPlayer();

    expect(screen.queryByText("Raise Your Fist")).toBeNull();
  });

  it("the play button asks the audio element to play", async () => {
    // Only the mobile transport labels its play button.
    isMobile.set(true);
    renderPlayer();

    await fireEvent.click(screen.getByLabelText("Afspelen"));

    expect(window.HTMLMediaElement.prototype.play).toHaveBeenCalled();
  });

  it("the state follows what the audio element reports", async () => {
    // togglePlay drives the element; the store is updated by its play/pause
    // events, which is what an OS media key or a car head unit triggers too.
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");

    await fireEvent.play(audioElement);
    expect(get(playerState).playing).toBe(true);

    await fireEvent.pause(audioElement);
    expect(get(playerState).playing).toBe(false);
  });

  it("next moves to the following track", async () => {
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText("Volgende")[0]);

    expect(get(currentTrack)).toEqual(SECOND);
  });

  it("next stops at the end of the queue", async () => {
    currentTrack.set(SECOND);
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText("Volgende")[0]);

    expect(get(currentTrack)).toEqual(SECOND);
  });

  it("next wraps around when everything repeats", async () => {
    currentTrack.set(SECOND);
    playerState.update((s) => ({ ...s, repeat: "all" }));
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText("Volgende")[0]);

    expect(get(currentTrack)).toEqual(FIRST);
  });

  it("next picks another track when shuffling", async () => {
    playerState.update((s) => ({ ...s, shuffle: true }));
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText("Volgende")[0]);

    expect(get(currentTrack)).toEqual(SECOND);
  });

  // A queue of six makes the point the two-track queue cannot: with only FIRST and
  // SECOND to draw from, a player that re-rolls on previous lands on the right track
  // by accident.
  it("previous comes back to the track shuffle came from", async () => {
    const queue = ["a", "b", "c", "d", "e", "f"].map((id) => ({ ...FIRST, id, title: id }));
    playlist.set(queue);
    currentTrack.set(queue[0]);
    playerState.update((s) => ({ ...s, shuffle: true }));
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText("Volgende")[0]);
    const landedOn = get(currentTrack);
    await fireEvent.click(screen.getByLabelText("Vorige"));

    expect(get(currentTrack).id).toBe("a");
    expect(landedOn.id).not.toBe("a");
  });

  it("next after previous returns to the track shuffle had already picked", async () => {
    const queue = ["a", "b", "c", "d", "e", "f"].map((id) => ({ ...FIRST, id, title: id }));
    playlist.set(queue);
    currentTrack.set(queue[0]);
    playerState.update((s) => ({ ...s, shuffle: true }));
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText("Volgende")[0]);
    const landedOn = get(currentTrack).id;
    await fireEvent.click(screen.getByLabelText("Vorige"));
    await fireEvent.click(screen.getAllByLabelText("Volgende")[0]);

    expect(get(currentTrack).id).toBe(landedOn);
  });

  it("previous moves back a track", async () => {
    currentTrack.set(SECOND);
    renderPlayer();

    await fireEvent.click(screen.getByLabelText("Vorige"));

    expect(get(currentTrack)).toEqual(FIRST);
  });

  describe("Now Playing", () => {
    it("opens on a tap on the mobile mini player", async () => {
      isMobile.set(true);
      renderPlayer();
      expect(screen.queryByTestId("now-playing")).toBeNull();

      await fireEvent.click(screen.getByText("Raise Your Fist"));

      expect(screen.getByTestId("now-playing")).toBeTruthy();
      expect(get(nowPlayingOpen)).toBe(true);
    });

    it("does not open from a tap on the play or next button", async () => {
      isMobile.set(true);
      renderPlayer();

      await fireEvent.click(screen.getByLabelText("Afspelen"));
      await fireEvent.click(screen.getAllByLabelText("Volgende")[0]);

      expect(screen.queryByTestId("now-playing")).toBeNull();
      expect(get(nowPlayingOpen)).toBe(false);
    });

    it("never opens on the desktop layout, even if asked to", () => {
      isMobile.set(false);
      nowPlayingOpen.set(true);

      renderPlayer();

      expect(screen.queryByTestId("now-playing")).toBeNull();
    });

    it("closes on its own chevron", async () => {
      // closeNowPlaying() also consumes the history entry openNowPlaying()
      // pushed; a real history.back() in jsdom is not what this test is
      // about, so it is stubbed the same way SidebarHeader's test does.
      vi.spyOn(window.history, "back").mockImplementation(() => {});
      isMobile.set(true);
      renderPlayer();
      await fireEvent.click(screen.getByText("Raise Your Fist"));
      expect(screen.getByTestId("now-playing")).toBeTruthy();

      await fireEvent.click(screen.getByLabelText("Sluiten"));

      expect(screen.queryByTestId("now-playing")).toBeNull();
      expect(get(nowPlayingOpen)).toBe(false);
    });
  });

  describe("lyrics", () => {
    /** Answers `getLyricsBySongId` with structured lyrics, everything else as usual. */
    function lyricsApi(lines) {
      return vi.fn(async (url) => {
        if (url.includes("/rest/getLyricsBySongId")) {
          return {
            ok: true,
            json: async () => ({
              "subsonic-response": {
                status: "ok",
                lyricsList: { structuredLyrics: { line: lines.map((value) => ({ value })) } },
              },
            }),
          };
        }
        return { ok: true, json: async () => ({ "subsonic-response": { status: "ok" } }) };
      });
    }

    it("shows a desktop lyrics button once LMS answers with lines for the track", async () => {
      globalThis.fetch = lyricsApi(["Raise your fist", "in the air"]);
      isMobile.set(false);
      renderPlayer();

      await waitFor(() => expect(screen.queryByLabelText("Lyrics")).toBeTruthy());

      await fireEvent.click(screen.getByLabelText("Lyrics"));

      expect(screen.getByText("Raise your fist")).toBeTruthy();
      expect(screen.getByText("in the air")).toBeTruthy();
    });

    it("shows no lyrics affordance when LMS has none for the track", async () => {
      globalThis.fetch = api();
      isMobile.set(false);
      renderPlayer();

      // Lets the (empty) lyrics fetch settle before asserting its absence.
      await new Promise((resolve) => setTimeout(resolve, 0));

      expect(screen.queryByLabelText("Lyrics")).toBeNull();
    });

    it("offers lyrics from the phone's Now Playing sheet once LMS answers with some", async () => {
      globalThis.fetch = lyricsApi(["One line only"]);
      isMobile.set(true);
      renderPlayer();
      await fireEvent.click(screen.getByText("Raise Your Fist"));
      expect(screen.getByTestId("now-playing")).toBeTruthy();

      await waitFor(() => expect(screen.queryByLabelText("Lyrics")).toBeTruthy());
      await fireEvent.click(screen.getByLabelText("Lyrics"));

      expect(screen.getByText("One line only")).toBeTruthy();
    });
  });

  describe("news of the hour", () => {
    /** Answers the two news calls with the statuses a test wants to see. */
    function newsApi({ latest = 200, stream = 200 } = {}) {
      return vi.fn(async (url) => {
        if (url.includes("/api/news/bulletins/latest")) {
          return { ok: latest === 200, status: latest, json: async () => ({ id: 7 }) };
        }
        if (url.includes("/api/news/bulletins/7/stream")) {
          return {
            ok: stream === 200,
            status: stream,
            blob: async () => new Blob(["mp3"], { type: "audio/mpeg" }),
          };
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ "subsonic-response": { status: "ok" } }),
        };
      });
    }

    it("says nothing is recorded when the server says exactly that", async () => {
      const spy = vi.spyOn(notify, "error");
      globalThis.fetch = newsApi({ latest: 404 });
      renderPlayer();

      await fireEvent.click(screen.getAllByLabelText("Nieuws van het uur")[0]);

      await waitFor(() => expect(spy).toHaveBeenCalledWith("Nog geen bulletin opgenomen"));
    });

    // The bulletin outgrew the proxy's buffer, so the audio never arrived and the
    // player blamed the recorder -- which had a fresh bulletin waiting the whole time.
    it("a bulletin that will not come through is not reported as a missing bulletin", async () => {
      const spy = vi.spyOn(notify, "error");
      globalThis.fetch = newsApi({ stream: 502 });
      renderPlayer();

      await fireEvent.click(screen.getAllByLabelText("Nieuws van het uur")[0]);

      await waitFor(() =>
        expect(spy).toHaveBeenCalledWith("Kon het nieuws niet afspelen", { detail: "HTTP 502" }),
      );
      expect(spy).not.toHaveBeenCalledWith("Nog geen bulletin opgenomen");
    });
  });

  it("the repeat button cycles through its modes", async () => {
    renderPlayer();
    const repeat = screen.getByLabelText("Herhalen");

    await fireEvent.click(repeat);
    expect(get(playerState).repeat).toBe("all");

    await fireEvent.click(repeat);
    expect(get(playerState).repeat).toBe("one");

    await fireEvent.click(repeat);
    expect(get(playerState).repeat).toBe("none");
  });

  it("the shuffle button toggles shuffling", async () => {
    renderPlayer();

    await fireEvent.click(screen.getByLabelText("Shuffle"));

    expect(get(playerState).shuffle).toBe(true);
  });

  it("the queue button is handed back to the parent", async () => {
    const ontoggleQueue = vi.fn();
    renderPlayer({ ontoggleQueue });

    await fireEvent.click(screen.getByLabelText("Wachtrij"));

    expect(ontoggleQueue).toHaveBeenCalled();
  });

  it("an empty queue has nothing to skip to", async () => {
    playlist.set([]);
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText("Volgende")[0]);

    expect(get(currentTrack)).toEqual(FIRST);
  });

  it("rating the track tells the server", async () => {
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText("4 sterren")[0]);

    await waitFor(() =>
      expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/rest/setRating"))).toBe(
        true,
      ),
    );
  });

  it("reports a rejected rating and puts the old one back", async () => {
    const spy = vi.spyOn(notify, "error");
    // Subsonic rejects with a 200, which is exactly what used to pass as a
    // success here.
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": { status: "failed", error: { code: 50, message: "Not authorized" } },
      }),
    }));
    currentTrack.set({ ...FIRST, userRating: 3 });
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText("5 sterren")[0]);

    await waitFor(() => expect(spy).toHaveBeenCalled());
    expect(spy.mock.calls[0][0]).toBe("Beoordeling kon niet worden opgeslagen");
    expect(get(currentTrack).userRating).toBe(3);
  });

  // Losing a scrobble does not stop the music, so it must not read as an
  // error the user has to act on.
  it("reports a failed scrobble as a warning, not an error", async () => {
    const warning = vi.spyOn(notify, "warning");
    const error = vi.spyOn(notify, "error");
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    });
    const { container } = renderPlayer();

    await fireEvent.play(container.querySelector("audio"));

    await waitFor(() =>
      expect(warning).toHaveBeenCalledWith("Scrobble mislukt", expect.anything()),
    );
    expect(error).not.toHaveBeenCalled();
  });

  // A listen that does not say where it happened cannot be split by device afterwards, and the
  // whole point of recording it is that the year can be read back per device.
  it("says where the play happened", async () => {
    const calls = [];
    globalThis.fetch = vi.fn(async (url) => {
      calls.push(url);
      return { ok: true, json: async () => ({ "subsonic-response": { status: "ok" } }) };
    });
    const { container } = renderPlayer();

    await fireEvent.play(container.querySelector("audio"));

    await waitFor(() => expect(calls.some((url) => url.includes("/rest/scrobble"))).toBe(true));
    const scrobble = calls.find((url) => url.includes("/rest/scrobble"));
    expect(scrobble).toContain("source=frontend");
  });

  it("reports a stream that will not load", async () => {
    const spy = vi.spyOn(notify, "error");
    const { container } = renderPlayer();

    await fireEvent.error(container.querySelector("audio"));

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith('"Raise Your Fist" kon niet worden geladen'),
    );
  });

  it("a rating the server accepted stays on screen", async () => {
    currentTrack.set({ ...FIRST, userRating: 0 });
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText("4 sterren")[0]);
    await settled();

    expect(screen.getAllByLabelText("4 sterren")[0].className).toContain("text-brand");
  });

  // Subsonic answers errors with HTTP 200 and a "failed" body, so a rating the
  // server refused used to keep its stars lit while nothing was stored.
  it("a rating the server refused does not stay on screen", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      json: async () => ({
        "subsonic-response": {
          status: "failed",
          error: { code: 60, message: "Wrong username or password." },
        },
      }),
    }));
    currentTrack.set({ ...FIRST, userRating: 0 });
    renderPlayer();

    await fireEvent.click(screen.getAllByLabelText("4 sterren")[0]);
    await settled();

    expect(screen.getAllByLabelText("4 sterren")[0].className).not.toContain("text-brand");
  });

  it("the album of the track can be opened", async () => {
    const onnavigate = vi.fn();
    renderPlayer({ onnavigate });

    await fireEvent.click(screen.getAllByText("Raise Your Fist")[0]);

    expect(onnavigate).toHaveBeenCalledWith("album:album-1");
  });

  it("the progress is followed while the track plays", async () => {
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "currentTime", { value: 30, writable: true });
    Object.defineProperty(audioElement, "duration", { value: 240, writable: true });

    await fireEvent.timeUpdate(audioElement);

    expect(get(playerState).progress).toBe(30);
  });

  it("the duration is taken from the loaded track", async () => {
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "duration", { value: 240, writable: true });

    await fireEvent.loadedMetadata(audioElement);

    expect(get(playerState).duration).toBe(240);
  });

  it("seeking moves to the clicked position", async () => {
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    Object.defineProperty(audioElement, "duration", { value: 200, writable: true });
    // Seeking uses the same length the bar is drawn with, so the element has to
    // have reported it.
    await fireEvent.loadedMetadata(audioElement);
    const bar = screen.getByLabelText("Door nummer spoelen");
    bar.getBoundingClientRect = () => ({ left: 0, width: 100 });

    await fireEvent.click(bar, { clientX: 50 });

    expect(audioElement.currentTime).toBe(100);
  });

  it("the volume bar sets the volume", async () => {
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    const bar = screen.getByLabelText("Volume");
    bar.getBoundingClientRect = () => ({ left: 0, width: 100 });

    await fireEvent.click(bar, { clientX: 25 });

    expect(audioElement.volume).toBeCloseTo(0.25);
  });

  it("dragging the volume to zero mutes", async () => {
    const { container } = renderPlayer();
    const audioElement = container.querySelector("audio");
    const bar = screen.getByLabelText("Volume");
    bar.getBoundingClientRect = () => ({ left: 0, width: 100 });

    await fireEvent.click(bar, { clientX: 0 });

    expect(audioElement.volume).toBe(0);
  });

  it("the artist of the track can be opened", async () => {
    const onnavigate = vi.fn();
    renderPlayer({ onnavigate });

    await fireEvent.click(screen.getAllByText("Angerfist")[0]);

    expect(onnavigate).toHaveBeenCalledWith("artist:artist-1");
  });

  describe("radio channels", () => {
    function radioApi(channels) {
      return vi.fn(async (url) => {
        if (url.includes("/api/radio/channels"))
          return { ok: true, json: async () => ({ channels }) };
        if (url.includes("/api/radio/time")) {
          return { ok: true, json: async () => ({ server_time: Date.now() / 1000 }) };
        }
        if (url.includes("/state"))
          return { ok: true, json: async () => ({ current: null, next: null }) };
        return { ok: true, json: async () => ({ "subsonic-response": { status: "ok" } }) };
      });
    }

    it("offers a choice when more than one channel is on air", async () => {
      globalThis.fetch = radioApi([
        { slug: "main", name: "Radio", filter: {} },
        { slug: "qdance", name: "Q-dance", filter: { label: "Q-dance Records" } },
      ]);
      renderPlayer();

      await fireEvent.click(screen.getByLabelText("Radio"));

      await waitFor(() => expect(screen.getByText("Q-dance")).toBeTruthy());
      expect(screen.getByText("Q-dance Records")).toBeTruthy();
      // Nothing is tuned in until a channel is picked.
      expect(get(radioChannel)).toBeNull();
    });

    it("tunes into the channel that was picked", async () => {
      globalThis.fetch = radioApi([
        { slug: "main", name: "Radio", filter: {} },
        { slug: "qdance", name: "Q-dance", filter: { label: "Q-dance Records" } },
      ]);
      renderPlayer();

      await fireEvent.click(screen.getByLabelText("Radio"));
      await waitFor(() => expect(screen.getByText("Q-dance")).toBeTruthy());
      await fireEvent.click(screen.getByText("Q-dance"));

      await waitFor(() => expect(get(radioChannel)).toBe("qdance"));
    });

    it("starts straight away when there is only one channel", async () => {
      globalThis.fetch = radioApi([{ slug: "main", name: "Radio", filter: {} }]);
      renderPlayer();

      await fireEvent.click(screen.getByLabelText("Radio"));

      await waitFor(() => expect(get(radioChannel)).toBe("main"));
    });
  });

  // The LG TV browser fires `timeupdate` only on a state change -- play, pause,
  // seek, ended -- and never on the periodic cadence the spec asks for, so the
  // bar used to sit still there until someone touched the transport.
  describe("a browser that does not fire timeupdate", () => {
    it("the position follows the element while it plays", async () => {
      vi.useFakeTimers();
      try {
        const { container } = renderPlayer();
        const audioElement = container.querySelector("audio");
        Object.defineProperty(audioElement, "duration", { value: 240, writable: true });
        Object.defineProperty(audioElement, "paused", { value: false, writable: true });
        audioElement.currentTime = 0;

        await fireEvent.play(audioElement);
        audioElement.currentTime = 30;
        // No `timeupdate` is dispatched at any point.
        await vi.advanceTimersByTimeAsync(300);

        expect(get(playerState).progress).toBe(30);
      } finally {
        vi.useRealTimers();
      }
    });

    it("the polling stops once the element is paused", async () => {
      vi.useFakeTimers();
      try {
        const { container } = renderPlayer();
        const audioElement = container.querySelector("audio");
        Object.defineProperty(audioElement, "duration", { value: 240, writable: true });
        Object.defineProperty(audioElement, "paused", { value: false, writable: true });

        await fireEvent.play(audioElement);
        audioElement.currentTime = 30;
        await vi.advanceTimersByTimeAsync(300);
        audioElement.paused = true;
        await fireEvent.pause(audioElement);
        audioElement.currentTime = 90;
        await vi.advanceTimersByTimeAsync(1000);

        expect(get(playerState).progress).toBe(30);
      } finally {
        vi.useRealTimers();
      }
    });
  });

  // A transcoded stream arrives chunked and without a `Content-Length`, which
  // leaves `duration` at `Infinity` on the TV.
  describe("a stream without a length of its own", () => {
    it("the track length is used instead", async () => {
      const { container } = renderPlayer();
      const audioElement = container.querySelector("audio");
      Object.defineProperty(audioElement, "duration", { value: Infinity, writable: true });

      await fireEvent.loadedMetadata(audioElement);

      expect(get(playerState).duration).toBe(240);
      expect(screen.getAllByText("4:00").length).toBeGreaterThan(0);
    });

    it("the bar is drawn from the track length", async () => {
      const { container } = renderPlayer();
      const audioElement = container.querySelector("audio");
      Object.defineProperty(audioElement, "duration", { value: Infinity, writable: true });
      audioElement.currentTime = 60;

      await fireEvent.timeUpdate(audioElement);

      const bar = screen.getByLabelText("Door nummer spoelen");
      expect(bar.firstElementChild.style.width).toBe("25%");
    });

    it("seeking is refused rather than throwing the position away", async () => {
      const { container } = renderPlayer();
      const audioElement = container.querySelector("audio");
      Object.defineProperty(audioElement, "duration", { value: Infinity, writable: true });
      currentTrack.set({ ...FIRST, duration: 0 });
      audioElement.currentTime = 42;
      const bar = screen.getByLabelText("Door nummer spoelen");
      bar.getBoundingClientRect = () => ({ left: 0, width: 100 });

      await fireEvent.click(bar, { clientX: 50 });

      expect(audioElement.currentTime).toBe(42);
    });
  });
});
