import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import VersionsTab from "../../src/lib/management/tabs/VersionsTab.svelte";

const SONG = {
  work_id: 5,
  title: "Together",
  artist: "Hysta",
  version_count: 2,
  canonical_track_id: 22,
  canonical_title: "Together (Radio Edit)",
  pinned_track_id: null,
  previous_canonical_track_id: 21,
  canonical_changed_at: "2026-09-26T10:00:00",
};

const DETAIL = {
  work_id: 5,
  title: "Together",
  artist: "Hysta",
  canonical_track_id: 22,
  pinned_track_id: null,
  previous_canonical_track_id: 21,
  canonical_changed_at: "2026-09-26T10:00:00",
  versions: [
    {
      track_id: 22,
      title: "Together (Radio Edit)",
      version_kind: "radio",
      file_path: "/mnt/music/EPs/__TODO/Together/01.flac",
      format: "flac",
      bitrate_kbps: 900,
      source: "label",
      is_official: true,
      rating: 5,
      plays: 3,
      is_canonical: true,
    },
    {
      track_id: 21,
      title: "Together",
      version_kind: "none",
      file_path: "/mnt/music/Soundcloud/hysta/Together.mp3",
      format: "mp3",
      bitrate_kbps: 130,
      source: "soundcloud",
      is_official: false,
      rating: null,
      plays: 40,
      is_canonical: false,
    },
  ],
};

function props() {
  return {
    API_BASE: "http://muma",
    getHeaders: () => ({ "x-api-key": "key" }),
    onMessage: vi.fn(),
    onError: vi.fn(),
  };
}

function mockApi() {
  return vi.fn(async (url, options = {}) => {
    if (options.method === "POST") return { ok: true, json: async () => ({ status: "ok" }) };
    if (url.includes("/api/songs/curation"))
      return { ok: true, json: async () => ({ items: [SONG], total: 1, page: 1, page_size: 50 }) };
    if (url.endsWith("/api/songs/ranking"))
      return {
        ok: true,
        json: async () => ({
          signature: "v2-lossless",
          prefer_lossless: true,
          pending_works: 0,
          changed_works: 1,
        }),
      };
    if (url.endsWith("/api/songs/5")) return { ok: true, json: async () => DETAIL };
    return { ok: false, status: 404, json: async () => ({}) };
  });
}

async function renderLoaded() {
  const view = render(VersionsTab, props());
  await waitFor(() => expect(screen.getByText("Together")).toBeTruthy());
  return view;
}

async function openSong() {
  await fireEvent.click(screen.getByText("Together").closest("button"));
  await waitFor(() => expect(screen.getAllByTestId("version-row")).toHaveLength(2));
}

function posts() {
  return globalThis.fetch.mock.calls.filter(([, options]) => options?.method === "POST");
}

describe("VersionsTab", () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists songs with several versions, sorted by version count first", async () => {
    await renderLoaded();
    const url = globalThis.fetch.mock.calls
      .map(([u]) => u)
      .find((u) => u.includes("/api/songs/curation"));
    expect(url).toContain("sort=versions");
    expect(screen.getByText("2 versies")).toBeTruthy();
  });

  it("flags a song whose automatic choice the rescore changed", async () => {
    await renderLoaded();
    expect(screen.getByText("Gewijzigd")).toBeTruthy();
    expect((await screen.findByTestId("ranking-status")).textContent).toContain("lossless eerst");
  });

  it("shows each version's source, format, kind and plays when opened", async () => {
    await renderLoaded();
    await openSong();
    expect(screen.getByText("Labelrelease")).toBeTruthy();
    expect(screen.getByText("SoundCloud")).toBeTruthy();
    expect(screen.getByText("FLAC")).toBeTruthy();
    expect(screen.getByText("MP3 128")).toBeTruthy();
    expect(screen.getByText("Radio edit")).toBeTruthy();
    expect(screen.getByText("40 keer gespeeld")).toBeTruthy();
    expect(screen.getByText("Was de beste")).toBeTruthy();
  });

  it("pins another version as best", async () => {
    await renderLoaded();
    await openSong();
    const [, ripRow] = screen.getAllByTestId("version-row");
    await fireEvent.click(ripRow.querySelector("button"));
    await waitFor(() => expect(posts()).toHaveLength(1));
    const [url, options] = posts()[0];
    expect(url).toBe("http://muma/api/songs/5/pin");
    expect(JSON.parse(options.body)).toEqual({ track_id: 21 });
  });

  it("accepts the rescore's choice", async () => {
    await renderLoaded();
    await openSong();
    await fireEvent.click(screen.getByText("Nieuwe keuze accepteren"));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(posts()[0][0]).toBe("http://muma/api/songs/5/dismiss-change");
  });

  it("offers a reset only for a pinned song", async () => {
    globalThis.fetch = vi.fn(async (url, options = {}) => {
      if (url.endsWith("/api/songs/5") && !options.method)
        return { ok: true, json: async () => ({ ...DETAIL, pinned_track_id: 21 }) };
      return mockApi()(url, options);
    });
    await renderLoaded();
    await openSong();
    await fireEvent.click(screen.getByText("Terug naar automatisch"));
    await waitFor(() => expect(posts()).toHaveLength(1));
    expect(JSON.parse(posts()[0][1].body)).toEqual({ track_id: null });
  });

  it("searches from the first page", async () => {
    await renderLoaded();
    const input = screen.getByPlaceholderText("Zoek op titel of artiest");
    await fireEvent.input(input, { target: { value: "hysta" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    await waitFor(() =>
      expect(
        globalThis.fetch.mock.calls.some(([u]) => u.includes("q=hysta") && u.includes("page=1")),
      ).toBe(true),
    );
  });
});
