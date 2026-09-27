import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";

// Issue #122: the label page's "Kanalen" section and its helpers.

const api = vi.hoisted(() => ({
  fetchMumaJson: vi.fn(),
  subsonicJson: vi.fn(),
}));

vi.mock("../../src/lib/mumaApi.js", async (importOriginal) => ({
  ...(await importOriginal()),
  apiBase: () => "/muma",
  getHeaders: () => ({ "X-API-Key": "k" }),
  fetchMumaJson: api.fetchMumaJson,
}));

vi.mock("../../src/lib/subsonic.js", async (importOriginal) => ({
  ...(await importOriginal()),
  subsonicJson: api.subsonicJson,
}));

import LabelChannels from "../../src/lib/LabelChannels.svelte";
import {
  cachedLabelChannels,
  channelAlbumView,
  channelDestination,
  clearLabelChannels,
  fetchLabelChannels,
} from "../../src/lib/labelChannels.js";

const TRAXTORM = {
  id: 3,
  platform: "soundcloud",
  name: "Traxtorm Records",
  track_count: 812,
  artist: null,
  album: "Soundcloud (Traxtorm Records)",
  source_url: "https://soundcloud.com/traxtormrecords",
};
const TUBE = {
  id: 4,
  platform: "youtube",
  name: "Traxtorm TV",
  track_count: 1,
  artist: null,
  album: "Youtube (Traxtorm TV)",
  source_url: null,
};

function albums(...names) {
  return {
    "subsonic-response": {
      searchResult3: {
        album: names.map((name, i) => ({ id: `al-${i}`, name })),
      },
    },
  };
}

beforeEach(() => {
  clearLabelChannels();
  api.fetchMumaJson.mockReset();
  api.subsonicJson.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("labelChannels helpers", () => {
  it("asks the endpoint by label name and remembers the answer", async () => {
    api.fetchMumaJson.mockResolvedValue([TRAXTORM]);
    expect(await fetchLabelChannels("Traxtorm & Co / NL")).toEqual([TRAXTORM]);
    expect(api.fetchMumaJson).toHaveBeenCalledWith(
      "/muma/api/channel-links/by-label?name=Traxtorm%20%26%20Co%20%2F%20NL",
      { headers: { "X-API-Key": "k" } },
    );
    expect(cachedLabelChannels("Traxtorm & Co / NL")).toEqual([TRAXTORM]);
  });

  it("finds the channel's album only by its exact name", async () => {
    api.subsonicJson.mockResolvedValue(
      albums("Soundcloud (Traxtorm Records Two)", "soundcloud (traxtorm records)"),
    );
    expect(await channelAlbumView(TRAXTORM)).toBe("album:al-1");
    api.subsonicJson.mockResolvedValue(albums("Soundcloud (Traxtorm)"));
    expect(await channelAlbumView(TRAXTORM)).toBeNull();
    api.subsonicJson.mockRejectedValue(new Error("down"));
    expect(await channelAlbumView(TRAXTORM)).toBeNull();
  });

  it("goes to the track list, else the source page, else a search", async () => {
    api.subsonicJson.mockResolvedValue(albums("Soundcloud (Traxtorm Records)"));
    expect(await channelDestination(TRAXTORM)).toEqual({ view: "album:al-0" });
    api.subsonicJson.mockResolvedValue(albums());
    expect(await channelDestination(TRAXTORM)).toEqual({
      url: TRAXTORM.source_url,
    });
    expect(await channelDestination(TUBE)).toEqual({
      view: "search:Traxtorm TV",
    });
  });
});

describe("LabelChannels", () => {
  function show(props = {}) {
    const onnavigate = vi.fn();
    const onmanage = vi.fn();
    const openUrl = vi.fn(async () => {});
    render(LabelChannels, {
      label: "Traxtorm",
      onnavigate,
      onmanage,
      platform: { system: { openUrl } },
      ...props,
    });
    return { onnavigate, onmanage, openUrl };
  }

  it("lists the linked channels with platform and track count", async () => {
    api.fetchMumaJson.mockResolvedValue([TRAXTORM, TUBE]);
    show();
    const rows = await screen.findAllByTestId("label-channel");
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("Traxtorm Records");
    expect(rows[0].textContent).toMatch(/812/);
    expect(rows[0].getAttribute("title")).toBe("SoundCloud");
    expect(rows[1].getAttribute("title")).toBe("YouTube");
    expect(screen.queryByTestId("label-channels-manage")).toBeNull();
  });

  it("opens the channel's track list, or its page on the platform", async () => {
    api.fetchMumaJson.mockResolvedValue([TRAXTORM]);
    api.subsonicJson.mockResolvedValue(albums("Soundcloud (Traxtorm Records)"));
    const { onnavigate, openUrl } = show();
    await fireEvent.click(await screen.findByTestId("label-channel"));
    await waitFor(() => expect(onnavigate).toHaveBeenCalledWith("album:al-0"));
    api.subsonicJson.mockResolvedValue(albums());
    await fireEvent.click(screen.getByTestId("label-channel"));
    await waitFor(() => expect(openUrl).toHaveBeenCalledWith(TRAXTORM.source_url));
  });

  it("shows nothing to a listener while loading or when no channel is linked", async () => {
    let resolve;
    api.fetchMumaJson.mockReturnValue(new Promise((r) => (resolve = r)));
    show();
    expect(screen.queryByTestId("label-channels")).toBeNull();
    resolve([]);
    await Promise.resolve();
    expect(screen.queryByTestId("label-channels")).toBeNull();
  });

  it("shows a curator the skeleton, then the empty line and the way to Koppelingen", async () => {
    let resolve;
    api.fetchMumaJson.mockReturnValue(new Promise((r) => (resolve = r)));
    const { onmanage } = show({ canManage: true });
    expect(screen.getByTestId("label-channels-skeleton")).toBeTruthy();
    resolve([]);
    expect(await screen.findByTestId("label-channels-empty")).toBeTruthy();
    await fireEvent.click(screen.getByTestId("label-channels-manage"));
    expect(onmanage).toHaveBeenCalled();
  });

  it("says a failure with a retry that loads again", async () => {
    api.fetchMumaJson.mockRejectedValueOnce(new Error("503")).mockResolvedValueOnce([TRAXTORM]);
    show();
    expect(await screen.findByTestId("section-error")).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: /opnieuw|retry/i }));
    expect(await screen.findByTestId("label-channel")).toBeTruthy();
  });

  it("shows the last answer at once on a revisit and refreshes it", async () => {
    api.fetchMumaJson.mockResolvedValue([TRAXTORM]);
    await fetchLabelChannels("Traxtorm");
    api.fetchMumaJson.mockReturnValue(new Promise(() => {}));
    show();
    expect(screen.getAllByTestId("label-channel")).toHaveLength(1);
    expect(api.fetchMumaJson).toHaveBeenCalledTimes(2);
  });
});
