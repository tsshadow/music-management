/**
 * The advanced search page: cluster pickers that OR within a kind, a preview that follows the
 * query through `getSongs`, and a save that writes the Kotlin tile spelling MuMa's other readers
 * (the home grid, Android Auto) open. Opened over an existing preset it PUTs instead of POSTs.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";

import PresetBuilder from "../../src/lib/PresetBuilder.svelte";
import MultiPicker from "../../src/lib/MultiPicker.svelte";
import { normalizePreset, presets } from "../../src/lib/presets.js";
import { credentials, mumaApiKey, mumaUser, viewMode } from "../../src/lib/store.js";

const SONGS = [{ id: "song-1", title: "Raise Your Fist", artist: "Angerfist", suffix: "flac" }];

/** LMS lists for the pickers, a `getSongs` page for the preview, and a MuMa id on save. */
function server() {
  return vi.fn(async (url, init) => {
    const u = String(url);
    const body = (payload) => ({ ok: true, json: async () => payload });
    if (u.includes("/rest/getGenres?")) {
      return body({
        "subsonic-response": {
          status: "ok",
          genres: { genre: [{ value: "Uptempo Hardcore" }, { value: "Hardstyle" }] },
        },
      });
    }
    if (u.includes("/rest/getRecordLabels?")) {
      return body({
        "subsonic-response": {
          status: "ok",
          recordLabels: { recordLabel: [{ value: "Masters of Hardcore" }] },
        },
      });
    }
    if (u.includes("/rest/getYears?")) {
      return body({ "subsonic-response": { status: "ok", years: { year: [{ value: "2024" }] } } });
    }
    if (u.includes("/rest/getTags?")) {
      return body({
        "subsonic-response": { status: "ok", tags: { tag: [{ value: "Dominator" }] } },
      });
    }
    if (u.includes("/rest/getArtistList?")) {
      return body({
        "subsonic-response": { status: "ok", artistList: { artist: [{ name: "Angerfist" }] } },
      });
    }
    if (u.includes("/rest/getSongs?")) {
      return body({ "subsonic-response": { status: "ok", songs: { song: SONGS } } });
    }
    if (u.includes("/dynamic-playlists") && init?.method === "POST") {
      return body({ status: "ok", id: 42 });
    }
    if (u.includes("/dynamic-playlists") && init?.method === "PUT") {
      return body({ status: "ok" });
    }
    if (u.includes("/dynamic-playlists")) {
      return body([]);
    }
    return body({});
  });
}

function songsCalls() {
  return globalThis.fetch.mock.calls.filter(([url]) => String(url).includes("/rest/getSongs?"));
}

describe("MultiPicker", () => {
  it("adds a suggestion on click and takes it out again on its ×", async () => {
    const onchange = vi.fn();
    const { rerender } = render(MultiPicker, {
      id: "p",
      label: "Genres",
      selected: [],
      options: ["Uptempo Hardcore", "Hardstyle"],
      onchange,
    });

    const input = screen.getByRole("combobox");
    await fireEvent.focus(input);
    await fireEvent.input(input, { target: { value: "hard" } });
    await fireEvent.click(screen.getByText("Hardstyle"));
    expect(onchange).toHaveBeenCalledWith(["Hardstyle"]);

    await rerender({ id: "p", label: "Genres", selected: ["Hardstyle"], options: [], onchange });
    await fireEvent.click(screen.getByLabelText("Hardstyle weghalen"));
    expect(onchange).toHaveBeenLastCalledWith([]);
  });

  it("takes whatever was typed on Enter, so a name the list lacks still counts", async () => {
    const onchange = vi.fn();
    render(MultiPicker, { id: "p", label: "Artiesten", selected: [], options: [], onchange });

    const input = screen.getByRole("combobox");
    await fireEvent.input(input, { target: { value: "  Angerfist " } });
    await fireEvent.keyDown(input, { key: "Enter" });

    expect(onchange).toHaveBeenCalledWith(["Angerfist"]);
  });
});

describe("PresetBuilder", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    credentials.set({ url: "", username: "user", password: "pw" });
    viewMode.set("songs");
    mumaUser.set({ id: 7, username: "user" });
    mumaApiKey.set("key");
    presets.set([]);
    globalThis.fetch = server();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("previews the query through getSongs with every picked cluster OR'd inside its kind", async () => {
    render(PresetBuilder, { onnavigate: vi.fn() });

    const genres = screen.getByLabelText("Genres");
    await fireEvent.focus(genres);
    await fireEvent.input(genres, { target: { value: "Uptempo" } });
    await waitFor(() => expect(screen.getByText("Uptempo Hardcore")).toBeTruthy());
    await fireEvent.click(screen.getByText("Uptempo Hardcore"));
    await fireEvent.focus(genres);
    await fireEvent.input(genres, { target: { value: "Hardstyle" } });
    await fireEvent.keyDown(genres, { key: "Enter" });

    await vi.advanceTimersByTimeAsync(400);
    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());

    const url = decodeURIComponent(String(songsCalls().at(-1)[0]));
    expect(url).toContain('{"name":"GENRE","value":["Uptempo Hardcore","Hardstyle"]}');
    expect(url).toContain('{"name":"LENGTH","value":"short"}');
    expect(url).toContain("count=50");
  });

  it("saves the query as a Kotlin-spelled tile and opens it", async () => {
    const onnavigate = vi.fn();
    render(PresetBuilder, { onnavigate });

    await fireEvent.click(screen.getByRole("radio", { name: "Sets" }));
    const festivals = screen.getByLabelText("Festivals");
    await fireEvent.input(festivals, { target: { value: "Dominator" } });
    await fireEvent.keyDown(festivals, { key: "Enter" });
    await fireEvent.input(screen.getByLabelText("Naam"), { target: { value: "Dominator sets" } });
    await fireEvent.click(screen.getByRole("button", { name: "Opslaan als snelkoppeling" }));

    await waitFor(() => expect(onnavigate).toHaveBeenCalledWith("preset:42"));
    const post = globalThis.fetch.mock.calls.find(([, init]) => init?.method === "POST");
    const sent = JSON.parse(post[1].body);
    expect(sent.name).toBe("Dominator sets");
    expect(JSON.parse(sent.params)).toMatchObject({
      festival: ["Dominator"],
      length: "long",
      pageKey: "sets",
    });
  });

  it("offers the Soort only for sets, previews and saves it", async () => {
    const onnavigate = vi.fn();
    render(PresetBuilder, { onnavigate });

    expect(screen.queryByLabelText("Soort")).toBeNull();
    await fireEvent.click(screen.getByRole("radio", { name: "Sets" }));
    await fireEvent.change(screen.getByLabelText("Soort"), { target: { value: "liveset" } });

    await vi.advanceTimersByTimeAsync(400);
    await waitFor(() => expect(String(songsCalls().at(-1)?.[0])).toContain("form=liveset"));

    await fireEvent.click(screen.getByRole("button", { name: "Opslaan als snelkoppeling" }));
    await waitFor(() => expect(onnavigate).toHaveBeenCalledWith("preset:42"));
    const post = globalThis.fetch.mock.calls.find(([, init]) => init?.method === "POST");
    expect(JSON.parse(JSON.parse(post[1].body).params)).toMatchObject({
      form: "liveset",
      length: "long",
    });
  });

  it("over an existing preset it starts filled in and PUTs on save", async () => {
    const existing = normalizePreset({
      id: 15,
      name: "Random Uptempo",
      params: JSON.stringify({
        genre: ["Uptempo Hardcore"],
        sortMethod: "Random",
        length: "short",
        size: 150,
      }),
    });
    const onnavigate = vi.fn();
    render(PresetBuilder, { preset: existing, onnavigate });

    expect(screen.getByText("Uptempo Hardcore")).toBeTruthy();
    expect(screen.getByLabelText("Naam")).toHaveValue("Random Uptempo");
    expect(screen.getByLabelText("Sortering")).toHaveValue("random");

    await fireEvent.click(screen.getByRole("button", { name: "Wijzigingen opslaan" }));

    await waitFor(() => expect(onnavigate).toHaveBeenCalledWith("preset:15"));
    const put = globalThis.fetch.mock.calls.find(([, init]) => init?.method === "PUT");
    expect(String(put[0])).toMatch(/dynamic-playlists\/15$/);
    expect(JSON.parse(JSON.parse(put[1].body).params)).toMatchObject({
      genre: ["Uptempo Hardcore"],
      size: 150,
    });
  });

  it("cannot save without a MuMa account, and says so", async () => {
    // A session without an id: the shared system key, not a person -- there is no user row to
    // hang a preset on. (Setting the store to null would be a logout, which also resets the
    // locale to the browser's, so the strings below would change language under the test.)
    mumaUser.set({ username: "shared" });
    render(PresetBuilder, { onnavigate: vi.fn() });

    await waitFor(() => expect(screen.getByText("Log in bij MuMa om op te slaan.")).toBeTruthy());
    const save = screen.getByText("Opslaan als snelkoppeling").closest("button");
    expect(save).toBeDisabled();
  });
});
