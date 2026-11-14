import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/svelte";
import { get } from "svelte/store";

vi.mock("../../src/lib/feeds.js", () => ({ resolveFeedChunk: vi.fn() }));
vi.mock("../../src/lib/queue.js", () => ({ startQueue: vi.fn() }));
vi.mock("../../src/lib/homeRankings.js", () => ({ resolveArtistView: vi.fn() }));
vi.mock("../../src/lib/genreTints.js", () => ({
  fetchGenreTints: vi.fn(async () => ({ hardcore: "#aa0000" })),
  tintFor: (tints, name) => (tints && tints[(name ?? "").toLowerCase()]) || null,
}));

import WrappedView from "../../src/lib/wrapped/WrappedView.svelte";
import WrappedHomeTile from "../../src/lib/wrapped/WrappedHomeTile.svelte";
import { resolveFeedChunk } from "../../src/lib/feeds.js";
import { startQueue } from "../../src/lib/queue.js";
import { resolveArtistView } from "../../src/lib/homeRankings.js";
import { currentTrack, wrappedOnHomeEnabled } from "../../src/lib/store.js";
import { ALL_CARDS, payloadWith } from "./wrappedFixture.js";

/** A fetcher that answers the periods call and every tab call. */
function api(tabPayload, { status = 200 } = {}) {
  return vi.fn(async (url) => {
    if (String(url).includes("/api/wrapped/periods")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ years: [{ year: 2025 }, { year: 2024 }] }),
      };
    }
    return {
      ok: status === 200,
      status,
      headers: { get: () => null },
      json: async () => (typeof tabPayload === "function" ? tabPayload(url) : tabPayload),
    };
  });
}

function fakePlatform(result = "shared") {
  return { system: { share: vi.fn(async () => result) } };
}

describe("WrappedView", () => {
  beforeEach(() => {
    window.history.replaceState(null, "", "/wrapped/2026/user");
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.history.replaceState(null, "", "/");
  });

  it("renders every card kind from a full payload, then the coverage card", async () => {
    render(WrappedView, {
      route: "2026/user",
      fetcher: api(payloadWith(ALL_CARDS)),
      platform: fakePlatform(),
    });

    await waitFor(() =>
      expect(screen.getAllByTestId("wrapped-card")).toHaveLength(ALL_CARDS.length),
    );
    const kinds = new Set(screen.getAllByTestId("wrapped-card").map((card) => card.dataset.kind));
    expect([...kinds].sort()).toEqual(["bars", "clock", "fact", "heatmap", "hero", "rank"]);
    expect(screen.getByTestId("wrapped-hours").children).toHaveLength(24);
    expect(screen.getByTestId("wrapped-heatmap").children).toHaveLength(7);
    expect(screen.getAllByTestId("wrapped-legend").length).toBeGreaterThan(0);
    expect(screen.getByTestId("wrapped-coverage")).toBeTruthy();
    expect(screen.getByTestId("wrapped-left-out").children).toHaveLength(2);
  });

  it("tints a genre card with its genre colour", async () => {
    render(WrappedView, {
      route: "2026/user",
      fetcher: api(payloadWith(ALL_CARDS)),
      platform: fakePlatform(),
    });
    await waitFor(() =>
      expect(document.querySelector('[data-card="top_genres"]').getAttribute("style")).toContain(
        "rgb(170, 0, 0)",
      ),
    );
  });

  it("shows only the coverage card when every card is blocked", async () => {
    const blocked = ALL_CARDS.map((card) => ({
      ...card,
      status: "blocked",
      reason: "no_arrival_date",
      data: null,
    }));
    render(WrappedView, {
      route: "2026/library",
      fetcher: api(payloadWith(blocked)),
      platform: fakePlatform(),
    });

    await waitFor(() => expect(screen.getByTestId("wrapped-coverage")).toBeTruthy());
    expect(screen.queryAllByTestId("wrapped-card")).toHaveLength(0);
  });

  it("says there are no listens on an empty user tab", async () => {
    const onnavigate = vi.fn();
    const empty = payloadWith([], {
      coverage: { listens: 0, linked: 0, unmatched: 0, left_out: [] },
    });
    render(WrappedView, {
      route: "2026/user",
      fetcher: api(empty),
      onnavigate,
      platform: fakePlatform(),
    });

    await waitFor(() => expect(screen.getByTestId("wrapped-empty")).toBeTruthy());
    const [listening, settings] = screen.getByTestId("wrapped-empty").querySelectorAll("button");
    await fireEvent.click(listening);
    await fireEvent.click(settings);
    expect(onnavigate).toHaveBeenCalledWith("listening");
    expect(onnavigate).toHaveBeenCalledWith("settings");
  });

  it("offers a retry when the tab cannot be loaded", async () => {
    const fetcher = api(payloadWith(ALL_CARDS.slice(0, 1)), { status: 500 });
    render(WrappedView, { route: "2026/user", fetcher, platform: fakePlatform() });

    const alert = await screen.findByRole("alert");
    const tabCalls = () =>
      fetcher.mock.calls.filter(([url]) => String(url).includes("/api/wrapped/user")).length;
    expect(tabCalls()).toBe(1);
    await fireEvent.click(alert.querySelector("button"));
    await waitFor(() => expect(tabCalls()).toBe(2));
  });

  it("shows the computing message while the server works out the tab", async () => {
    let release;
    const wait = vi.fn(() => new Promise((resolve) => (release = resolve)));
    let tabCalls = 0;
    // The periods call and the tab call race, so each is answered by its URL.
    const byUrl = vi.fn(async (url) => {
      if (String(url).includes("/periods"))
        return { ok: true, status: 200, json: async () => ({ years: [] }) };
      tabCalls += 1;
      if (tabCalls === 1)
        return { ok: false, status: 503, headers: { get: () => "1" }, json: async () => ({}) };
      return { ok: true, status: 200, json: async () => payloadWith(ALL_CARDS.slice(0, 1)) };
    });
    render(WrappedView, { route: "2026/user", fetcher: byUrl, wait, platform: fakePlatform() });

    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toMatch(/worked out|uitgerekend/),
    );
    release();
    await waitFor(() => expect(screen.getAllByTestId("wrapped-card")).toHaveLength(1));
  });

  it("switches tabs and periods in place, without a new history entry", async () => {
    const onnavigate = vi.fn();
    const before = window.history.length;
    render(WrappedView, {
      route: "2026/user",
      fetcher: api(payloadWith(ALL_CARDS.slice(0, 1))),
      onnavigate,
      platform: fakePlatform(),
    });
    await screen.findAllByTestId("wrapped-card");

    const library = screen
      .getAllByRole("button")
      .find((button) => button.getAttribute("aria-pressed") === "false");
    await fireEvent.click(library);
    expect(onnavigate).toHaveBeenLastCalledWith("wrapped:2026/library");
    expect(window.location.pathname).toBe("/wrapped/2026/library");

    const select = screen.getByRole("combobox");
    expect([...select.options].map((option) => option.value)).toEqual([
      "2026",
      "2025",
      "2024",
      "custom",
    ]);
    await fireEvent.change(select, { target: { value: "2025" } });
    expect(onnavigate).toHaveBeenLastCalledWith("wrapped:2025/user");
    expect(window.history.length).toBe(before);
  });

  it("applies a custom range and refuses a bad one", async () => {
    const onnavigate = vi.fn();
    render(WrappedView, {
      route: "2026/user",
      fetcher: api(payloadWith(ALL_CARDS.slice(0, 1))),
      onnavigate,
      platform: fakePlatform(),
    });
    await screen.findAllByTestId("wrapped-card");

    await fireEvent.change(screen.getByRole("combobox"), { target: { value: "custom" } });
    const form = screen.getByTestId("wrapped-range");
    const [from, to] = form.querySelectorAll("input");
    await fireEvent.input(from, { target: { value: "2026-06-30" } });
    await fireEvent.input(to, { target: { value: "2026-03-01" } });
    await fireEvent.submit(form);
    expect(screen.getByTestId("wrapped-range").querySelector('[role="alert"]')).toBeTruthy();

    await fireEvent.input(from, { target: { value: "2026-03-01" } });
    await fireEvent.input(to, { target: { value: "2026-06-30" } });
    await fireEvent.submit(screen.getByTestId("wrapped-range"));
    expect(onnavigate).toHaveBeenLastCalledWith("wrapped:2026-03-01_2026-06-30/user");
  });

  it("rewrites the bare /wrapped to the running year's user tab", async () => {
    const onnavigate = vi.fn();
    render(WrappedView, {
      route: "",
      fetcher: api(payloadWith([])),
      onnavigate,
      platform: fakePlatform(),
    });
    const year = new Date().getFullYear();
    expect(onnavigate).toHaveBeenCalledWith(`wrapped:${year}/user`);
    expect(window.location.pathname).toBe(`/wrapped/${year}/user`);
  });

  it("plays the tracks of a card", async () => {
    const songs = [{ id: "s1" }, { id: "s2" }];
    resolveFeedChunk.mockResolvedValue({ songs, failed: false });
    render(WrappedView, {
      route: "2026/user",
      fetcher: api(payloadWith(ALL_CARDS)),
      platform: fakePlatform(),
    });
    await screen.findAllByTestId("wrapped-card");

    const card = document.querySelector('[data-card="top_tracks"]');
    const play = [...card.querySelectorAll("button")].find(
      (button) => button.querySelector("svg") && !button.getAttribute("aria-label"),
    );
    await fireEvent.click(play);
    await waitFor(() => expect(startQueue).toHaveBeenCalledWith(songs, expect.any(Object)));
    expect(resolveFeedChunk.mock.calls[0][0]).toEqual([
      "Labels/Track One.flac",
      "Labels/Track Two.flac",
      "Labels/Track Three.flac",
    ]);
    expect(get(currentTrack)).toEqual(songs[0]);
  });

  it("does not start a queue when no track resolves", async () => {
    resolveFeedChunk.mockResolvedValue({ songs: [], failed: false });
    render(WrappedView, {
      route: "2026/user",
      fetcher: api(payloadWith(ALL_CARDS)),
      platform: fakePlatform(),
    });
    await screen.findAllByTestId("wrapped-card");
    const card = document.querySelector('[data-card="top_tracks"]');
    const play = [...card.querySelectorAll("button")].find(
      (button) => !button.getAttribute("aria-label"),
    );
    await fireEvent.click(play);
    await waitFor(() => expect(resolveFeedChunk).toHaveBeenCalled());
    expect(startQueue).not.toHaveBeenCalled();
  });

  it("opens an artist page, a search for an unknown artist, and a genre page", async () => {
    const onnavigate = vi.fn();
    resolveArtistView.mockResolvedValueOnce("artist:42").mockResolvedValueOnce(null);
    render(WrappedView, {
      route: "2026/user",
      fetcher: api(payloadWith(ALL_CARDS)),
      onnavigate,
      platform: fakePlatform(),
    });
    await screen.findAllByTestId("wrapped-card");

    const artistCard = document.querySelector('[data-card="top_artists"]');
    const artistButton = [...artistCard.querySelectorAll("button")].find(
      (button) => button.textContent === "Artist A",
    );
    await fireEvent.click(artistButton);
    await waitFor(() => expect(onnavigate).toHaveBeenCalledWith("artist:42"));

    const discovery = document.querySelector('[data-card="discovery"]');
    await fireEvent.click(
      [...discovery.querySelectorAll("button")].find((button) => button.textContent === "Artist D"),
    );
    await waitFor(() => expect(onnavigate).toHaveBeenCalledWith("search:Artist D"));

    const genres = document.querySelector('[data-card="top_genres"]');
    await fireEvent.click(
      [...genres.querySelectorAll("button")].find((button) => button.textContent === "Uptempo"),
    );
    expect(onnavigate).toHaveBeenCalledWith("genre:Uptempo");
  });

  it("shares a card as an image without the account name", async () => {
    const platform = fakePlatform("saved");
    const renderImage = vi.fn(() => "data:image/png;base64,AAAA");
    render(WrappedView, {
      route: "2026/user",
      fetcher: api(payloadWith(ALL_CARDS)),
      platform,
      renderImage,
    });
    await screen.findAllByTestId("wrapped-card");

    const card = document.querySelector('[data-card="top_artists"]');
    await fireEvent.click(card.querySelector("button[aria-label]"));
    await waitFor(() => expect(platform.system.share).toHaveBeenCalledOnce());
    const [image] = platform.system.share.mock.calls[0];
    expect(image.dataUrl).toBe("data:image/png;base64,AAAA");
    expect(image.fileName).toBe("muma-wrapped-2026-top-artists.png");
    const [face, options] = renderImage.mock.calls[0];
    expect(face.id).toBe("top_artists");
    expect(Object.keys(options).sort()).toEqual(["brand", "period", "tint"]);
  });

  it("reports a share that fails", async () => {
    const platform = { system: { share: vi.fn(async () => Promise.reject(new Error("no"))) } };
    const errors = vi.spyOn(console, "error").mockImplementation(() => {});
    render(WrappedView, {
      route: "2026/user",
      fetcher: api(payloadWith(ALL_CARDS.slice(0, 1))),
      platform,
      renderImage: () => "data:",
    });
    await screen.findAllByTestId("wrapped-card");
    await fireEvent.click(document.querySelector('[data-card="title"] button[aria-label]'));
    await waitFor(() => expect(errors).toHaveBeenCalled());
  });
});

describe("WrappedHomeTile", () => {
  afterEach(() => {
    cleanup();
    wrappedOnHomeEnabled.set(true);
  });

  it("offers the running year in December and opens its user tab", async () => {
    const onnavigate = vi.fn();
    render(WrappedHomeTile, { onnavigate, now: new Date(2026, 11, 3) });
    const tile = screen.getByTestId("home-wrapped-tile");
    expect(tile.textContent).toContain("2026");
    await fireEvent.click(tile);
    expect(onnavigate).toHaveBeenCalledWith("wrapped:2026/user");
  });

  it("offers the year that ended in January", () => {
    render(WrappedHomeTile, { onnavigate: vi.fn(), now: new Date(2027, 0, 10) });
    expect(screen.getByTestId("home-wrapped-tile").textContent).toContain("2026");
  });

  it("stays away outside the season or when switched off", () => {
    render(WrappedHomeTile, { onnavigate: vi.fn(), now: new Date(2026, 5, 1) });
    expect(screen.queryByTestId("home-wrapped-tile")).toBeNull();
    cleanup();
    wrappedOnHomeEnabled.set(false);
    render(WrappedHomeTile, { onnavigate: vi.fn(), now: new Date(2026, 11, 1) });
    expect(screen.queryByTestId("home-wrapped-tile")).toBeNull();
  });
});
