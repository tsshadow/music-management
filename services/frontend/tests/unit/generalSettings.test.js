import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import GeneralSettings from "../../src/lib/settings/GeneralSettings.svelte";
import { get } from "svelte/store";
import { credentials, DEFAULT_TRACK_PAGE_SIZE, trackPageSize } from "../../src/lib/store.js";

function mockUser(user = {}) {
  return vi.fn(async () => ({
    ok: true,
    json: async () => ({
      "subsonic-response": {
        status: "ok",
        user: {
          username: "user",
          uiArtistReleaseSortMethod: 8,
          subsonicArtistListMode: 0,
          feedbackBackend: 0,
          listenbrainzToken: "",
          ...user,
        },
      },
    }),
  }));
}

async function saveAndGetQuery() {
  await fireEvent.click(screen.getByText("Wijzigingen opslaan"));
  let query;
  await waitFor(() => {
    query = globalThis.fetch.mock.calls
      .map((c) => c[0])
      .find((url) => url.includes("/rest/updateUser"));
    expect(query).toBeTruthy();
  });
  return query;
}

describe("GeneralSettings", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    globalThis.fetch = mockUser();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    trackPageSize.set(DEFAULT_TRACK_PAGE_SIZE);
  });

  it("the number of tracks a list fetches is the listener's to change", async () => {
    render(GeneralSettings);
    await waitFor(() => expect(screen.getByLabelText("Nummers per keer")).toBeTruthy());

    await fireEvent.change(screen.getByLabelText("Nummers per keer"), { target: { value: "200" } });

    expect(get(trackPageSize)).toBe(200);
  });

  it("no longer shows the audio settings the server never read", async () => {
    render(GeneralSettings);

    await waitFor(() => expect(screen.getByText("Interface")).toBeTruthy());
    expect(screen.queryByText("Audio (Web Player)")).toBeNull();
    expect(screen.queryByText("Transcoding Modus")).toBeNull();
    expect(screen.queryByText("ReplayGain Modus")).toBeNull();
  });

  it("no longer offers scrobbling toggles -- scrobbling is on for everyone", async () => {
    render(GeneralSettings);

    await waitFor(() => expect(screen.getByText("Interface")).toBeTruthy());
    expect(screen.queryByText("Muma Scrobbler")).toBeNull();
    expect(screen.queryByText("Scrobbling Systeem")).toBeNull();
  });

  it("no longer hands out Subsonic tokens -- that is an admin task", async () => {
    render(GeneralSettings);

    await waitFor(() => expect(screen.getByText("Interface")).toBeTruthy());
    expect(screen.queryByText("Genereer Nieuw")).toBeNull();
    expect(screen.queryByText("Subsonic API Key (Token)")).toBeNull();
  });

  it("saves only the settings the server actually accepts", async () => {
    render(GeneralSettings);
    await waitFor(() => expect(screen.getByText("Interface")).toBeTruthy());

    const query = await saveAndGetQuery();

    for (const dropped of [
      "uiTranscodingMode",
      "uiTranscodingFormat",
      "uiTranscodingBitrate",
      "uiReplayGainMode",
      "scrobblingBackend",
      "mumaScrobblingEnabled",
      "subsonicToken",
    ]) {
      expect(query).not.toContain(dropped);
    }
    expect(query).toContain("uiArtistReleaseSortMethod=8");
    expect(query).toContain("feedbackBackend=0");
  });

  it("keeps a stored sort method of 0 instead of substituting an invalid enum", async () => {
    // The old fallback turned an unset/0 value into 107, which is not a valid
    // ReleaseSortMethod and got written straight back to the database.
    globalThis.fetch = mockUser({ uiArtistReleaseSortMethod: 0 });

    render(GeneralSettings);
    await waitFor(() => expect(screen.getByText("Interface")).toBeTruthy());

    const query = await saveAndGetQuery();
    expect(query).toContain("uiArtistReleaseSortMethod=0");
    expect(query).not.toContain("107");
  });

  it("falls back to the server default when the value is missing entirely", async () => {
    globalThis.fetch = mockUser({ uiArtistReleaseSortMethod: undefined });

    render(GeneralSettings);
    await waitFor(() => expect(screen.getByText("Interface")).toBeTruthy());

    const query = await saveAndGetQuery();
    expect(query).toContain("uiArtistReleaseSortMethod=8");
  });
});
