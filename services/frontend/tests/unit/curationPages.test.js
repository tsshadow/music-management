import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ArtistView from "../../src/lib/ArtistView.svelte";
import GenreEdit from "../../src/lib/curation/GenreEdit.svelte";
import ArtistEdit from "../../src/lib/curation/ArtistEdit.svelte";
import {
  credentials,
  currentTrack,
  deduplicateEnabled,
  mumaUser,
  playerState,
  playlist,
  userPermissions,
  viewMode,
  subsonicToken,
} from "../../src/lib/store.js";

const ARTIST = { id: "artist-1", name: "Angerfist", album: [] };

function subsonicFetch(curationBody = {}) {
  return vi.fn(async (url) => {
    if (url.includes("/rest/getArtist?")) {
      return {
        ok: true,
        json: async () => ({ "subsonic-response": { status: "ok", artist: ARTIST } }),
      };
    }
    if (url.includes("/api/curation/genres/")) {
      return { ok: true, json: async () => curationBody };
    }
    if (url.includes("/api/curation/artists/")) {
      return { ok: true, json: async () => curationBody };
    }
    if (url.includes("/api/rules/genres")) {
      return { ok: true, json: async () => [] };
    }
    return { ok: true, json: async () => ({ "subsonic-response": { status: "ok" } }) };
  });
}

beforeEach(() => {
  credentials.set({ url: "", username: "demo-user", password: "pw" });
  subsonicToken.set({ username: "demo-user", token: "test-subsonic-token" });
  viewMode.set("songs");
  deduplicateEnabled.set(false);
  playlist.set([]);
  currentTrack.set(null);
  playerState.set({ playing: false });
  userPermissions.set([]);
  mumaUser.set(null);
  globalThis.fetch = subsonicFetch();
});

afterEach(() => {
  vi.restoreAllMocks();
  userPermissions.set([]);
  mumaUser.set(null);
});

describe("the pencil on the artist page", () => {
  it("is not offered to a user who may not manage rules", async () => {
    render(ArtistView, { artistId: "artist-1", onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Angerfist")).toBeTruthy());

    expect(screen.queryByLabelText("Artiest bewerken")).toBeNull();
  });

  it("is offered to a user who may", async () => {
    userPermissions.set(["rules.manage"]);
    render(ArtistView, { artistId: "artist-1", onnavigate: vi.fn() });
    await waitFor(() => expect(screen.getByText("Angerfist")).toBeTruthy());

    expect(screen.getByLabelText("Artiest bewerken")).toBeTruthy();
  });

  it("navigates to the edit page for the artist being viewed", async () => {
    userPermissions.set(["rules.manage"]);
    const onnavigate = vi.fn();
    render(ArtistView, { artistId: "artist-1", onnavigate });
    await waitFor(() => expect(screen.getByText("Angerfist")).toBeTruthy());

    screen.getByLabelText("Artiest bewerken").click();

    expect(onnavigate).toHaveBeenCalledWith("artist-edit:artist-1");
  });
});

describe("the artist edit page", () => {
  it("trades the LMS id for the name MuMa knows, so a refresh still works", async () => {
    globalThis.fetch = subsonicFetch({
      name: "Angerfist",
      artist_id: 7,
      mbid: null,
      in_library: true,
      external_ids: [],
      aliases: [],
      genre_rules: [],
      track_count: 143,
    });

    render(ArtistEdit, { artistId: "artist-1", onback: vi.fn() });

    await waitFor(() => expect(screen.getByText("143 tracks in de bibliotheek")).toBeTruthy());
    const called = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(called.some((url) => url.includes("/api/curation/artists/Angerfist"))).toBe(true);
  });
});

describe("the genre edit page", () => {
  const genre = (over = {}) => ({
    name: "Industrial Hardcore",
    genre_id: 12,
    state: "white",
    editable: true,
    occurrences: 40,
    parents: ["Hardcore"],
    children: [],
    ...over,
  });

  it("shows the hierarchy of an accepted genre", async () => {
    globalThis.fetch = subsonicFetch(genre());
    render(GenreEdit, { name: "Industrial Hardcore", onback: vi.fn() });

    await waitFor(() => expect(screen.getByText("Valt onder")).toBeTruthy());
    expect(screen.getByText("Hardcore")).toBeTruthy();
  });

  it("offers no form for a rejected genre, and says why", async () => {
    // Curation decides whether a genre exists; a rejected one is not in the library,
    // so a hierarchy for it would be a rule that can never fire.
    globalThis.fetch = subsonicFetch(genre({ state: "black", editable: false }));
    render(GenreEdit, { name: "Arts", onback: vi.fn() });

    await waitFor(() =>
      expect(screen.getByText("Dit genre is niet goedgekeurd door de curatie")).toBeTruthy(),
    );
    expect(screen.queryByText("Valt onder")).toBeNull();
  });

  it("shows the genre's current hardness", async () => {
    globalThis.fetch = subsonicFetch(genre({ hardness: 45 }));
    render(GenreEdit, { name: "Industrial Hardcore", onback: vi.fn() });

    await waitFor(() => expect(screen.getByLabelText("Hardheid")).toBeTruthy());
    expect(screen.getByLabelText("Hardheid").value).toBe("45");
  });

  it("refuses to save a hardness value outside 0-100", async () => {
    globalThis.fetch = subsonicFetch(genre());
    render(GenreEdit, { name: "Industrial Hardcore", onback: vi.fn() });
    await waitFor(() => expect(screen.getByLabelText("Hardheid")).toBeTruthy());

    const input = screen.getByLabelText("Hardheid");
    await fireEvent.input(input, { target: { value: "150" } });
    await fireEvent.click(screen.getByText("Opslaan"));

    await waitFor(() =>
      expect(screen.getByText("Moet een geheel getal tussen 0 en 100 zijn, of leeg.")).toBeTruthy(),
    );
    const calledUrls = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(calledUrls.some((url) => url.includes("/hardness"))).toBe(false);
  });

  it("saves a valid hardness value", async () => {
    globalThis.fetch = subsonicFetch(genre());
    render(GenreEdit, { name: "Industrial Hardcore", onback: vi.fn() });
    await waitFor(() => expect(screen.getByLabelText("Hardheid")).toBeTruthy());

    const input = screen.getByLabelText("Hardheid");
    await fireEvent.input(input, { target: { value: "80" } });
    await fireEvent.click(screen.getByText("Opslaan"));

    await waitFor(() => expect(screen.getByText("Hardheid opgeslagen.")).toBeTruthy());
    const call = globalThis.fetch.mock.calls.find(([url]) => url.includes("/hardness"));
    expect(call).toBeTruthy();
    expect(call[1].method).toBe("PUT");
    expect(JSON.parse(call[1].body)).toEqual({ hardness: 80 });
  });
});
