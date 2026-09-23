/**
 * The voice screen's state machine: a clear command plays, a question shows tappable options and
 * re-runs the resolver on an answer, and a request that resolves to nothing says why rather than
 * hanging. `platform.speech` is a fake here -- the parser and the resolver behind `interpret()` are
 * `core/voice`'s to test; this component only has to render what came back and drive the same
 * queue a preset or a Home card uses.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";

import VoiceView from "../../src/lib/VoiceView.svelte";
import {
  credentials,
  currentTrack,
  mumaApiKey,
  playerState,
  playlist,
} from "../../src/lib/store.js";

/** Answers a `/rest/<method>` URL with `body`, and anything else with `{}`. */
function lms(routes) {
  return vi.fn(async (url) => {
    const match = Object.entries(routes).find(([path]) => String(url).includes(path));
    return {
      ok: true,
      json: async () => (match ? match[1] : { "subsonic-response": { status: "ok" } }),
    };
  });
}

/**
 * A `platform.speech` fake: `interpret` answers each call with the next entry of `results`, and
 * `fireFinal` drives the `onFinal` subscription the way a real recognizer's result would.
 *
 * @param {{supported?: boolean, results?: object[]}} [options]
 */
function fakeSpeech({ supported = true, results = [] } = {}) {
  let finalHandler = null;
  const queue = [...results];
  return {
    supported,
    start: vi.fn(async () => {}),
    stop: vi.fn(),
    onPartial: vi.fn(() => () => {}),
    onFinal: vi.fn((handler) => {
      finalHandler = handler;
      return () => {};
    }),
    interpret: vi.fn(async () => queue.shift()),
    vocabulary: vi.fn(async () => ({ title: "Wat verstaat MuMa", html: "voorbeelden" })),
    trace: vi.fn(async () => ({ traces: [] })),
    fireFinal(payload) {
      finalHandler(payload);
    },
  };
}

const CLEAR_PLAY = {
  explanation: {
    heard: "speel hardstyle af",
    genre: "Hardstyle",
    order: "released",
    understood: "Hardstyle",
  },
  resolution: {
    kind: "play",
    query: {
      type: "filtered",
      method: "getSongs",
      params: {
        clusters: '[{"name":"GENRE","value":["Hardstyle"]},{"name":"LENGTH","value":"short"}]',
        sortMethod: "OriginalDateDescAndRelease",
      },
    },
    trace: [{ label: "raw", text: '"speel hardstyle af"' }],
  },
};

const ASK_ALBUM_OR_PLAYLIST = {
  explanation: { heard: "speel thunderdome af", question: "thunderdome" },
  resolution: {
    kind: "ask",
    question: { prompt: "thunderdome", options: ["album", "playlist"] },
    trace: [],
  },
};

const ANSWERED_ALBUM = {
  explanation: { heard: "speel thunderdome af", album: "Thunderdome" },
  resolution: {
    kind: "play",
    query: { type: "item", kind: "album", id: "42", name: "Thunderdome" },
    trace: [],
  },
};

const NO_MATCH = {
  explanation: { heard: "asdkjasd", reason: "nothing the utterance named is in the library" },
  resolution: { kind: "nothing", trace: [] },
};

const HARDSTYLE_SONGS = [{ id: "s1", title: "Wildstylez", artist: "Wildstylez" }];
const THUNDERDOME_TRACKS = [{ id: "t1", title: "Thunderdome Anthem", artist: "Various" }];

describe("VoiceView", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    mumaApiKey.set("key");
    playlist.set([]);
    currentTrack.set(null);
    playerState.set({ playing: false });
    // Overridden per test with `lms(...)`; a bare default keeps the account-sync calls `mumaApiKey`
    // triggers from failing on `undefined.json()` in the tests that do not care about fetch at all.
    globalThis.fetch = lms({});
  });

  afterEach(() => vi.restoreAllMocks());

  it("offers nothing at all when the platform has no speech recogniser", () => {
    render(VoiceView, { platform: { speech: fakeSpeech({ supported: false }) } });

    expect(screen.queryByLabelText("Microfoon")).toBeNull();
    expect(screen.getByText(/niet beschikbaar in de browser/i)).toBeTruthy();
  });

  it("plays a clear command through the same queue a preset uses", async () => {
    globalThis.fetch = lms({
      "/rest/getSongs?": {
        "subsonic-response": { status: "ok", songs: { song: HARDSTYLE_SONGS } },
      },
    });
    const speech = fakeSpeech({ results: [CLEAR_PLAY] });
    render(VoiceView, { platform: { speech } });

    speech.fireFinal({ text: "speel hardstyle af", alternatives: [] });

    await waitFor(() => expect(get(playlist)).toEqual(HARDSTYLE_SONGS));
    expect(get(currentTrack)).toEqual(HARDSTYLE_SONGS[0]);
    expect(get(playerState).playing).toBe(true);
    expect(await screen.findByText(/Hardstyle wordt afgespeeld/)).toBeTruthy();
  });

  it("puts up a question, answers it by tapping an option, and plays what that resolves to", async () => {
    globalThis.fetch = lms({
      "/rest/getAlbum?": {
        "subsonic-response": { status: "ok", album: { song: THUNDERDOME_TRACKS } },
      },
    });
    const speech = fakeSpeech({ results: [ASK_ALBUM_OR_PLAYLIST, ANSWERED_ALBUM] });
    render(VoiceView, { platform: { speech } });

    speech.fireFinal({ text: "speel thunderdome af", alternatives: [] });

    await screen.findByText(/Bedoel je.*thunderdome/);
    expect(screen.getByRole("button", { name: "Album" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Afspeellijst" })).toBeTruthy();

    await fireEvent.click(screen.getByRole("button", { name: "Album" }));

    expect(speech.interpret).toHaveBeenLastCalledWith(
      expect.objectContaining({ text: "speel thunderdome af", pinned: "album" }),
    );
    await waitFor(() => expect(get(playlist)).toEqual(THUNDERDOME_TRACKS));
  });

  it("explains why nothing played and offers a way to try again", async () => {
    const speech = fakeSpeech({ results: [NO_MATCH] });
    render(VoiceView, { platform: { speech } });

    speech.fireFinal({ text: "asdkjasd", alternatives: [] });

    expect(await screen.findByText("nothing the utterance named is in the library")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Opnieuw" })).toBeTruthy();
  });
});
