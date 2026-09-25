import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import PlaylistsTab from "../../src/lib/management/tabs/PlaylistsTab.svelte";
import { notifications, dismissAll } from "../../src/lib/notifications.js";

const USER = { id: 1, username: "user" };
const PLAYLIST = {
  id: 7,
  name: "Hardcore Favorites",
  params: JSON.stringify({
    song_type: "track",
    genres: ["Hardcore", "Uptempo"],
    rating_range: [60, 100],
    sort_method: "newest",
    size: 500,
  }),
};

function props(overrides = {}) {
  return {
    API_BASE: "http://muma",
    apiKey: "key",
    users: [USER],
    playlists: [PLAYLIST],
    selectedUser: USER,
    getHeaders: (extra = {}) => ({ "x-api-key": "key", ...extra }),
    fetchPlaylists: vi.fn(),
    onSelectUser: vi.fn(),
    onMessage: vi.fn(),
    onError: vi.fn(),
    ...overrides,
  };
}

function mockApi({
  saveOk = true,
  deleteOk = true,
  tracks = [{ id: 1, title: "Raise Your Fist", artist: "Angerfist" }],
} = {}) {
  return vi.fn(async (url, options = {}) => {
    if (url.includes("/api/rules")) {
      return {
        ok: true,
        json: async () => ({
          genres: [
            { id: 1, name: "Hardcore" },
            { id: 2, name: "Uptempo" },
          ],
        }),
      };
    }
    if (url.includes("/tracks")) return { ok: true, json: async () => tracks };
    if (options.method === "DELETE") return { ok: deleteOk, json: async () => ({}) };
    if (options.method === "POST" || options.method === "PUT")
      return { ok: saveOk, json: async () => ({}) };
    return { ok: true, json: async () => ({}) };
  });
}

describe("PlaylistsTab", () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists the playlists of the selected user", () => {
    render(PlaylistsTab, props());

    expect(screen.getByText("Hardcore Favorites")).toBeTruthy();
  });

  it("summarises what a playlist selects on", () => {
    render(PlaylistsTab, props());

    expect(
      screen.getByText(/track • Hardcore, Uptempo • Rating: 60-100 • Sort: newest • Size: 500/),
    ).toBeTruthy();
  });

  it("falls back to the old rule format", () => {
    const playlist = {
      id: 8,
      name: "Legacy",
      params: JSON.stringify({ rules: [{ column: "genre", value: "Hardcore" }] }),
    };

    render(PlaylistsTab, props({ playlists: [playlist] }));

    expect(screen.getByText("genre=Hardcore")).toBeTruthy();
  });

  it("shows a query string that is not JSON as it is", () => {
    const playlist = { id: 8, name: "Legacy", params: "genre=Hardcore&size=100" };

    render(PlaylistsTab, props({ playlists: [playlist] }));

    expect(screen.getByText("genre=Hardcore • size=100")).toBeTruthy();
  });

  it("shows a dash for a playlist without rules", () => {
    render(PlaylistsTab, props({ playlists: [{ id: 8, name: "Empty", params: "" }] }));

    expect(screen.getByText("-")).toBeTruthy();
  });

  it("says so when the user has no playlists", () => {
    render(PlaylistsTab, props({ playlists: [] }));

    expect(screen.getByText("Geen dynamic playlists gevonden.")).toBeTruthy();
  });

  it("picking another user reloads their playlists", async () => {
    const onSelectUser = vi.fn();
    const fetchPlaylists = vi.fn();
    const { container } = render(PlaylistsTab, props({ onSelectUser, fetchPlaylists }));

    // The options carry whole user objects, so pick by index rather than by value.
    const picker = container.querySelector("select");
    picker.selectedIndex = 1;
    await fireEvent.change(picker);

    expect(onSelectUser).toHaveBeenCalled();
    expect(fetchPlaylists).toHaveBeenCalled();
  });

  it("a new playlist starts from the defaults", async () => {
    render(PlaylistsTab, props());

    await fireEvent.click(screen.getByText("NIEUWE PLAYLIST"));

    expect(screen.getByText("Nieuwe Dynamic Playlist")).toBeTruthy();
    expect(screen.getByLabelText("Playlist Naam").value).toBe("");
  });

  it("editing a playlist fills the editor with its rules", async () => {
    render(PlaylistsTab, props());

    await fireEvent.click(screen.getByTitle("Bewerken"));

    expect(screen.getByText("Afspeellijst Bewerken")).toBeTruthy();
    expect(screen.getByLabelText("Playlist Naam").value).toBe("Hardcore Favorites");
    expect(screen.getByLabelText("Type").value).toBe("track");
  });

  it("a playlist whose rules cannot be read falls back to the defaults", async () => {
    render(PlaylistsTab, props({ playlists: [{ id: 8, name: "Broken", params: "{not json" }] }));

    await fireEvent.click(screen.getByTitle("Bewerken"));

    expect(screen.getByLabelText("Type").value).toBe("both");
  });

  it("saving a new playlist posts it for the selected user", async () => {
    const onMessage = vi.fn();
    render(PlaylistsTab, props({ onMessage }));
    await fireEvent.click(screen.getByText("NIEUWE PLAYLIST"));
    await fireEvent.input(screen.getByLabelText("Playlist Naam"), {
      target: { value: "Nieuwe lijst" },
    });

    await fireEvent.click(screen.getByText("PLAYLIST OPSLAAN"));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Playlist opgeslagen"));
    const [url, options] = globalThis.fetch.mock.calls.find(([, o]) => o?.method === "POST");
    expect(url).toBe("http://muma/api/users/1/dynamic-playlists");
    expect(JSON.parse(options.body).name).toBe("Nieuwe lijst");
  });

  it("saving an existing playlist puts it", async () => {
    const onMessage = vi.fn();
    render(PlaylistsTab, props({ onMessage }));
    await fireEvent.click(screen.getByTitle("Bewerken"));

    await fireEvent.click(screen.getByText("PLAYLIST OPSLAAN"));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Playlist bijgewerkt"));
    const [url] = globalThis.fetch.mock.calls.find(([, o]) => o?.method === "PUT");
    expect(url).toBe("http://muma/api/users/1/dynamic-playlists/7");
  });

  it("a playlist without a name is not saved", async () => {
    render(PlaylistsTab, props());
    await fireEvent.click(screen.getByText("NIEUWE PLAYLIST"));
    globalThis.fetch.mockClear();

    await fireEvent.click(screen.getByText("PLAYLIST OPSLAAN"));

    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("reports a save the server refused", async () => {
    globalThis.fetch = mockApi({ saveOk: false });
    const onError = vi.fn();
    render(PlaylistsTab, props({ onError }));
    await fireEvent.click(screen.getByTitle("Bewerken"));

    await fireEvent.click(screen.getByText("PLAYLIST OPSLAAN"));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Kon playlist niet opslaan."));
  });

  it("deleting a playlist asks first", async () => {
    window.confirm.mockReturnValue(false);
    render(PlaylistsTab, props());
    globalThis.fetch.mockClear();

    await fireEvent.click(screen.getByTitle("Verwijderen"));

    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("a confirmed delete removes the playlist", async () => {
    const onMessage = vi.fn();
    const fetchPlaylists = vi.fn();
    render(PlaylistsTab, props({ onMessage, fetchPlaylists }));

    await fireEvent.click(screen.getByTitle("Verwijderen"));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Playlist verwijderd."));
    expect(fetchPlaylists).toHaveBeenCalled();
  });

  it("reports a delete the server refused", async () => {
    globalThis.fetch = mockApi({ deleteOk: false });
    const onError = vi.fn();
    render(PlaylistsTab, props({ onError }));

    await fireEvent.click(screen.getByTitle("Verwijderen"));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Kon playlist niet verwijderen."));
  });

  it("previewing shows the tracks the rules select", async () => {
    render(PlaylistsTab, props());

    await fireEvent.click(screen.getByTitle("Tracks bekijken"));

    await waitFor(() => expect(screen.getByText("Raise Your Fist")).toBeTruthy());
    expect(
      globalThis.fetch.mock.calls.some(
        ([url]) => url === "http://muma/api/users/1/dynamic-playlists/7/tracks",
      ),
    ).toBe(true);
  });

  it("says so when the rules select nothing", async () => {
    globalThis.fetch = mockApi({ tracks: [] });
    render(PlaylistsTab, props());

    await fireEvent.click(screen.getByTitle("Tracks bekijken"));

    await waitFor(() =>
      expect(screen.getByText("Geen tracks gevonden die voldoen aan de regels.")).toBeTruthy(),
    );
  });

  it("previewing without a user selected asks for nothing", async () => {
    render(PlaylistsTab, props({ selectedUser: null }));
    globalThis.fetch.mockClear();

    await fireEvent.click(screen.getByTitle("Tracks bekijken"));

    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("restoring the defaults asks for a user first", async () => {
    render(PlaylistsTab, props({ selectedUser: null }));
    globalThis.fetch.mockClear();

    await fireEvent.click(screen.getByText("DEFAULTS"));

    expect(get(notifications).map((n) => n.message)).toContain("Selecteer eerst een gebruiker");
    dismissAll();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("restoring the defaults seeds them once confirmed", async () => {
    const fetchPlaylists = vi.fn();
    render(PlaylistsTab, props({ fetchPlaylists }));

    await fireEvent.click(screen.getByText("DEFAULTS"));

    await waitFor(() =>
      expect(
        globalThis.fetch.mock.calls.some(
          ([url]) => url === "http://muma/api/users/1/dynamic-playlists/seed-defaults",
        ),
      ).toBe(true),
    );
  });
});
