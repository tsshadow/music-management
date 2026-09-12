import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/svelte";
import TrackList from "../../src/lib/TrackList.svelte";
import { credentials, currentTrack, playlist } from "../../src/lib/store.js";
import { offline } from "../../src/lib/subsonic.js";

const SONG = {
  id: "1",
  title: "Incoming",
  artist: "Angerfist",
  album: "Close Combat",
  duration: 210,
  size: 8_400_000,
  bitRate: 320,
};
const SET = {
  id: "2",
  title: "Defqon.1 2024",
  artist: "Angerfist",
  album: "Live",
  duration: 5400,
  size: 216_000_000,
  bitRate: 320,
};

/**
 * @param {object} [options]
 * @returns {object}
 */
function shell({ states = { 1: "none", 2: "none" }, supported = true, ...rest } = {}) {
  const handlers = [];
  return {
    emit: (event) => handlers.forEach((handler) => handler(event)),
    storage: {
      supported,
      stateOf: vi.fn(async (ids) =>
        Object.fromEntries(ids.map((id) => [id, states[id] ?? "none"])),
      ),
      download: vi.fn(async () => ({ requested: 1, unknown: 0 })),
      remove: vi.fn(async () => {}),
      query: vi.fn(async () => ({ "subsonic-response": { status: "ok" } })),
      onProgress: vi.fn((handler) => {
        handlers.push(handler);
        return () => {};
      }),
      ...rest,
    },
  };
}

describe("TrackList download state", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    playlist.set([]);
    currentTrack.set(null);
    offline.set(false);
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
  });

  afterEach(() => {
    offline.set(false);
    vi.restoreAllMocks();
  });

  // One call for the whole list, which is the entire reason the plugin takes a
  // batch: a list of two hundred rows must not be two hundred bridge hops.
  it("asks about every rendered row in one call", async () => {
    const platform = shell({ states: { 1: "done", 2: "queued" } });

    render(TrackList, { tracks: [SONG, SET], platform, onnavigate: vi.fn() });

    await waitFor(() => expect(platform.storage.stateOf).toHaveBeenCalledOnce());
    expect(platform.storage.stateOf).toHaveBeenCalledWith(["1", "2"]);
  });

  it("shows a glyph for a row that is downloaded and none for a row that is not", async () => {
    const platform = shell({ states: { 1: "done", 2: "none" } });

    render(TrackList, { tracks: [SONG, SET], platform, onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getAllByTestId("download-glyph")).toHaveLength(1));
    expect(screen.getByTestId("download-glyph").dataset.state).toBe("done");
  });

  it("follows the progress event for a row it is showing", async () => {
    const platform = shell({ states: { 1: "queued" } });
    render(TrackList, { tracks: [SONG], platform, onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByTestId("download-glyph")).toBeTruthy());
    platform.emit({ id: "1", state: "done", progress: 100 });

    await waitFor(() => expect(screen.getByTestId("download-glyph").dataset.state).toBe("done"));
  });

  it("ignores a progress event for a row it is not showing", async () => {
    const platform = shell({ states: { 1: "none" } });
    render(TrackList, { tracks: [SONG], platform, onnavigate: vi.fn() });

    await waitFor(() => expect(platform.storage.stateOf).toHaveBeenCalled());
    platform.emit({ id: "99", state: "done", progress: 100 });

    expect(screen.queryByTestId("download-glyph")).toBeNull();
  });

  it("asks nothing at all in a browser tab", async () => {
    const platform = shell({ supported: false });

    render(TrackList, { tracks: [SONG], platform, onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Incoming")).toBeTruthy());
    expect(platform.storage.stateOf).not.toHaveBeenCalled();
    expect(screen.queryByTitle("Downloaden naar apparaat")).toBeNull();
  });

  it("starts a short track straight away, with no question asked", async () => {
    const platform = shell();
    render(TrackList, { tracks: [SONG], platform, onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByTitle("Downloaden naar apparaat")).toBeTruthy());
    await fireEvent.click(screen.getByTitle("Downloaden naar apparaat"));

    expect(screen.queryByTestId("set-size-confirm")).toBeNull();
    expect(platform.storage.download).toHaveBeenCalledWith(["1"], { pin: true });
  });

  // A set is hundreds of megabytes; the functional design asks for the size
  // line before it is spent.
  it("shows a set's size before downloading it", async () => {
    const platform = shell();
    render(TrackList, { tracks: [SET], platform, onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByTitle("Downloaden naar apparaat")).toBeTruthy());
    await fireEvent.click(screen.getByTitle("Downloaden naar apparaat"));

    const sheet = screen.getByTestId("set-size-confirm");
    expect(screen.getByTestId("set-size")).toHaveTextContent("216 MB");
    expect(screen.getByText(/grootte die de bibliotheek/i)).toBeTruthy();
    expect(platform.storage.download).not.toHaveBeenCalled();

    await fireEvent.click(within(sheet).getByRole("button", { name: "Downloaden naar apparaat" }));
    expect(platform.storage.download).toHaveBeenCalledWith(["2"], { pin: true });
  });

  it("says so when the set's size is a guess from the bitrate", async () => {
    const platform = shell();
    const guessed = { ...SET, size: undefined };
    render(TrackList, { tracks: [guessed], platform, onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByTitle("Downloaden naar apparaat")).toBeTruthy());
    await fireEvent.click(screen.getByTitle("Downloaden naar apparaat"));

    expect(screen.getByText(/geschat uit de bitrate/i)).toBeTruthy();
    expect(screen.getByTestId("set-size")).toHaveTextContent("216 MB");
  });

  it("offers to remove a download instead of starting one, once it is there", async () => {
    const platform = shell({ states: { 1: "done" } });
    render(TrackList, { tracks: [SONG], platform, onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByTitle("Download verwijderen")).toBeTruthy());
    await fireEvent.click(screen.getByTitle("Download verwijderen"));

    expect(platform.storage.remove).toHaveBeenCalledWith(["1"]);
  });

  it("offers a retry on a row whose download failed", async () => {
    const platform = shell({ states: { 1: "failed" } });
    render(TrackList, { tracks: [SONG], platform, onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByTitle("Downloaden naar apparaat")).toBeTruthy());
  });
});

describe("TrackList cover art offline", () => {
  beforeEach(() => {
    credentials.set({ url: "https://lms.example", username: "user", password: "pw" });
    offline.set(false);
  });

  afterEach(() => {
    offline.set(false);
    vi.restoreAllMocks();
  });

  it("uses the server's cover art while there is a connection", async () => {
    const platform = shell();

    render(TrackList, {
      tracks: [{ ...SONG, coverArt: "art-1" }],
      platform,
      onnavigate: vi.fn(),
    });

    await waitFor(() => expect(screen.getByText("Incoming")).toBeTruthy());
    const image = document.querySelector("img");
    expect(image.getAttribute("src")).toContain("/rest/getCoverArt?id=art-1");
    expect(platform.storage.query).not.toHaveBeenCalled();
  });

  it("takes the artwork off the device when there is none", async () => {
    const platform = shell({
      query: vi.fn(async () => ({
        "subsonic-response": { status: "ok", url: "https://localhost/_capacitor_file_/a.jpg" },
      })),
    });
    offline.set(true);

    render(TrackList, {
      tracks: [{ ...SONG, coverArt: "art-2" }],
      platform,
      onnavigate: vi.fn(),
    });

    await waitFor(() =>
      expect(document.querySelector("img").getAttribute("src")).toBe(
        "https://localhost/_capacitor_file_/a.jpg",
      ),
    );
  });

  it("keeps the placeholder for art this device never cached", async () => {
    const platform = shell({
      query: vi.fn(async () => ({
        "subsonic-response": { status: "failed", error: { code: 70 } },
      })),
    });
    offline.set(true);

    render(TrackList, {
      tracks: [{ ...SONG, coverArt: "art-3" }],
      platform,
      onnavigate: vi.fn(),
    });

    await waitFor(() => expect(platform.storage.query).toHaveBeenCalled());
    expect(document.querySelector("img").getAttribute("src")).toBe("/images/spotify-fallback.svg");
  });
});
