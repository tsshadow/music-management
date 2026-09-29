/**
 * The BPM browse page: pick a tempo, see what plays at it, play it as a queue.
 *
 * The API calls themselves are covered in bpm.test.js; here they are stubbed so the page's own
 * behaviour is what is tested -- which request a chip, the tolerance, the reliability switch and
 * the genre picker send, how a coarse value is shown, and what the play button queues.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/svelte";
import { get } from "svelte/store";

import BpmView from "../../src/lib/BpmView.svelte";
import {
  credentials,
  currentTrack,
  playerState,
  playlist,
  subsonicToken,
} from "../../src/lib/store.js";

vi.mock("../../src/lib/bpm.js", async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    fetchBpmHistogram: (...args) => globalThis.__fetchBpmHistogram(...args),
    loadBpmPage: (...args) => globalThis.__loadBpmPage(...args),
  };
});

const HISTOGRAM = {
  bins: [
    { bpm: 150, count: 3, high: 1, medium: 0, low: 2 },
    { bpm: 152, count: 10, high: 0, medium: 6, low: 4 },
    { bpm: 200, count: 4, high: 0, medium: 0, low: 4 },
  ],
  genres: [
    { name: "Hardstyle", count: 12 },
    { name: "Frenchcore", count: 4 },
  ],
  default_tolerance: 2,
  summary: { tracks: 17 },
};

const SONGS = [
  {
    id: "s1",
    title: "Coarse One",
    artist: "Someone",
    path: "EPs/1.mp3",
    mumaBpm: { bpm: 152, source: "tag", confidence: "medium", folded: false, approximate: true },
  },
  {
    id: "s2",
    title: "Measured One",
    artist: "Someone",
    path: "EPs/2.mp3",
    mumaBpm: {
      bpm: 150.02,
      source: "measured",
      confidence: "high",
      folded: false,
      approximate: false,
    },
  },
];

/** The quick chip for `bpm` (the histogram has a bar with the same number). */
async function chip(bpm) {
  const chips = await screen.findByTestId("bpm-chips");
  return within(chips).getByRole("button", { name: new RegExp(`^${bpm}\\b`) });
}

function page(extra = {}) {
  return {
    songs: SONGS,
    total: 2,
    nextOffset: null,
    unresolved: 0,
    approximate: true,
    failed: false,
    ...extra,
  };
}

describe("BpmView", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    subsonicToken.set({ username: "user", token: "test-subsonic-token" });
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    globalThis.__fetchBpmHistogram = vi.fn(async () => HISTOGRAM);
    globalThis.__loadBpmPage = vi.fn(async () => page());
  });

  it("starts with the chips, their counts and a prompt, and loads no list yet", async () => {
    render(BpmView, { onnavigate: vi.fn() });
    // 150 ± 2 covers the 150 and 152 bins.
    await waitFor(async () => expect((await chip(150)).textContent).toContain("13"));
    expect(screen.getByText(/Kies een tempo of een bereik/)).toBeTruthy();
    expect(globalThis.__loadBpmPage).not.toHaveBeenCalled();
  });

  it("a chip lists the tracks at that tempo with their BPM, coarse ones marked", async () => {
    render(BpmView, { onnavigate: vi.fn() });
    await fireEvent.click(await chip(150));

    await waitFor(() => expect(screen.getByText("Coarse One")).toBeTruthy());
    const [params, auth] = globalThis.__loadBpmPage.mock.calls[0];
    expect(params).toEqual({ bpm: 150, tol: null, min_confidence: null, genre: null });
    expect(auth).toContain("u=user");
    const pills = screen.getAllByTestId("bpm-pill").map((pill) => pill.textContent.trim());
    expect(pills).toEqual(["≈152 BPM", "150 BPM"]);
    expect(screen.getByTestId("bpm-coarse-note")).toBeTruthy();
    expect(screen.getByTestId("bpm-count").textContent).toContain("2 nummers");
  });

  it("the tolerance, the reliability switch and the genre go into the request", async () => {
    render(BpmView, { onnavigate: vi.fn() });
    await fireEvent.click(await chip(150));
    await fireEvent.click(screen.getByRole("button", { name: "±1" }));
    expect(globalThis.__loadBpmPage.mock.lastCall[0]).toMatchObject({ bpm: 150, tol: 1 });

    await fireEvent.click(screen.getByTestId("bpm-reliable"));
    expect(globalThis.__loadBpmPage.mock.lastCall[0]).toMatchObject({ min_confidence: "medium" });
    expect(globalThis.__fetchBpmHistogram.mock.lastCall[0]).toEqual({
      reliable: true,
      genre: null,
    });

    await waitFor(() => expect(screen.getByRole("option", { name: /Frenchcore/ })).toBeTruthy());
    await fireEvent.change(screen.getByLabelText("Genre"), { target: { value: "Frenchcore" } });
    expect(globalThis.__loadBpmPage.mock.lastCall[0]).toMatchObject({ genre: "Frenchcore" });
  });

  it("a typed range replaces the picked tempo", async () => {
    render(BpmView, { onnavigate: vi.fn() });
    await fireEvent.click(await chip(150));
    await fireEvent.change(screen.getByLabelText("van"), { target: { value: "170" } });
    expect(globalThis.__loadBpmPage.mock.lastCall[0]).toEqual({
      bpm_from: 170,
      bpm_to: null,
      min_confidence: null,
      genre: null,
    });
  });

  it("a bar of the histogram picks its tempo", async () => {
    render(BpmView, { onnavigate: vi.fn() });
    await fireEvent.click(await screen.findByRole("button", { name: "200 BPM: 4 nummers" }));
    expect(globalThis.__loadBpmPage.mock.lastCall[0]).toMatchObject({ bpm: 200 });
  });

  it("play queues the list in its order and starts it", async () => {
    render(BpmView, { onnavigate: vi.fn() });
    await fireEvent.click(await chip(150));
    await fireEvent.click(await screen.findByTestId("bpm-play"));
    expect(get(playlist).map((song) => song.id)).toEqual(["s1", "s2"]);
    expect(get(currentTrack).id).toBe("s1");
    expect(get(playerState).playing).toBe(true);
  });

  it("an empty answer says so, and suggests switching reliability off when it is on", async () => {
    globalThis.__loadBpmPage = vi.fn(async () => page({ songs: [], total: 0, approximate: false }));
    render(BpmView, { onnavigate: vi.fn() });
    await fireEvent.click(await screen.findByTestId("bpm-reliable"));
    await fireEvent.click(await chip(230));
    await waitFor(() => expect(screen.getByText(/Zet Betrouwbaar uit/)).toBeTruthy());
  });

  it("a failed load offers a retry", async () => {
    globalThis.__loadBpmPage = vi.fn(async () => page({ failed: true }));
    render(BpmView, { onnavigate: vi.fn() });
    await fireEvent.click(await chip(150));
    await waitFor(() => expect(screen.getByRole("button", { name: /opnieuw/i })).toBeTruthy());
  });
});
