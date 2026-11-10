import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";

// Issue #122: the label page's "Kanalen" section and its helpers; #126: the artist page and
// the label edit page, with unlink.

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
  cachedLinkedChannels,
  channelAlbumView,
  channelDestination,
  clearLinkedChannels,
  fetchLinkedChannels,
  unlinkChannel,
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
  clearLinkedChannels();
  api.fetchMumaJson.mockReset();
  api.subsonicJson.mockReset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("labelChannels helpers", () => {
  it("asks the endpoint by label name and remembers the answer", async () => {
    api.fetchMumaJson.mockResolvedValue([TRAXTORM]);
    expect(await fetchLinkedChannels("label", "Traxtorm & Co / NL")).toEqual([TRAXTORM]);
    expect(api.fetchMumaJson).toHaveBeenCalledWith(
      "/muma/api/channel-links/by-label?name=Traxtorm%20%26%20Co%20%2F%20NL",
      { headers: { "X-API-Key": "k" } },
    );
    expect(cachedLinkedChannels("label", "Traxtorm & Co / NL")).toEqual([TRAXTORM]);
    expect(cachedLinkedChannels("artist", "Traxtorm & Co / NL")).toBeUndefined();
  });

  it("asks the artist endpoint by artist name, cached apart from a label of that name", async () => {
    api.fetchMumaJson.mockResolvedValue([TUBE]);
    expect(await fetchLinkedChannels("artist", "D-Sturb")).toEqual([TUBE]);
    expect(api.fetchMumaJson).toHaveBeenCalledWith(
      "/muma/api/channel-links/by-artist?name=D-Sturb",
      { headers: { "X-API-Key": "k" } },
    );
    expect(cachedLinkedChannels("artist", "D-Sturb")).toEqual([TUBE]);
    expect(cachedLinkedChannels("label", "D-Sturb")).toBeUndefined();
  });

  it("refuses a kind it has no endpoint for", async () => {
    await expect(fetchLinkedChannels("genre", "x")).rejects.toThrow(/genre/);
    await expect(unlinkChannel("genre", "x", TUBE)).rejects.toThrow(/genre/);
    expect(api.fetchMumaJson).not.toHaveBeenCalled();
  });

  it("unlinks a channel and drops it from the cached answer", async () => {
    api.fetchMumaJson.mockResolvedValueOnce([TRAXTORM, TUBE]);
    await fetchLinkedChannels("label", "Traxtorm");
    api.fetchMumaJson.mockResolvedValueOnce({ status: "unlinked", queued: 3 });
    expect(await unlinkChannel("label", "Traxtorm", TUBE)).toEqual({
      status: "unlinked",
      queued: 3,
    });
    expect(api.fetchMumaJson).toHaveBeenLastCalledWith("/muma/api/channel-links/channels/4/label", {
      method: "DELETE",
      headers: { "X-API-Key": "k" },
    });
    expect(cachedLinkedChannels("label", "Traxtorm")).toEqual([TRAXTORM]);
    api.fetchMumaJson.mockResolvedValueOnce({ status: "unlinked", queued: 0 });
    await unlinkChannel("artist", "Nobody", TUBE);
    expect(cachedLinkedChannels("artist", "Nobody")).toBeUndefined();
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
    const onmessage = vi.fn();
    const onerror = vi.fn();
    render(LabelChannels, {
      name: "Traxtorm",
      onmessage,
      onerror,
      onnavigate,
      onmanage,
      platform: { system: { openUrl } },
      ...props,
    });
    return { onnavigate, onmanage, openUrl, onmessage, onerror };
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
    await fetchLinkedChannels("label", "Traxtorm");
    api.fetchMumaJson.mockReturnValue(new Promise(() => {}));
    show();
    expect(screen.getAllByTestId("label-channel")).toHaveLength(1);
    expect(api.fetchMumaJson).toHaveBeenCalledTimes(2);
  });
  it("defaults to a label and offers no unlink outside the edit page", async () => {
    api.fetchMumaJson.mockResolvedValue([TRAXTORM]);
    show();
    await screen.findByTestId("label-channel");
    expect(api.fetchMumaJson.mock.calls[0][0]).toContain("/by-label?name=Traxtorm");
    expect(screen.getByTestId("label-channels").dataset.kind).toBe("label");
    expect(screen.queryByTestId("label-channel-unlink")).toBeNull();
  });

  it("lists an artist's channels from the artist endpoint", async () => {
    api.fetchMumaJson.mockResolvedValue([TUBE]);
    show({ kind: "artist", name: "D-Sturb" });
    expect((await screen.findAllByTestId("label-channel"))[0].textContent).toContain("Traxtorm TV");
    expect(api.fetchMumaJson.mock.calls[0][0]).toBe(
      "/muma/api/channel-links/by-artist?name=D-Sturb",
    );
    expect(screen.getByTestId("label-channels").dataset.kind).toBe("artist");
  });

  it("tells a curator no channel is linked to this artist", async () => {
    api.fetchMumaJson.mockResolvedValue([]);
    show({ kind: "artist", name: "D-Sturb", canManage: true });
    expect((await screen.findByTestId("label-channels-empty")).textContent).toMatch(
      /artiest|artist/i,
    );
  });

  it("unlinks a channel on the edit page and says so", async () => {
    api.fetchMumaJson.mockResolvedValueOnce([TRAXTORM, TUBE]);
    const { onmessage, onerror } = show({ canManage: true, canUnlink: true });
    const buttons = await screen.findAllByTestId("label-channel-unlink");
    expect(buttons).toHaveLength(2);
    expect(buttons[1].getAttribute("aria-label")).toContain("Traxtorm TV");
    api.fetchMumaJson.mockResolvedValueOnce({ status: "unlinked", queued: 1 });
    await fireEvent.click(buttons[1]);
    await waitFor(() => expect(screen.getAllByTestId("label-channel")).toHaveLength(1));
    expect(api.fetchMumaJson).toHaveBeenLastCalledWith(
      "/muma/api/channel-links/channels/4/label",
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(onmessage).toHaveBeenCalledWith(expect.stringContaining("Traxtorm TV"));
    expect(onerror).not.toHaveBeenCalled();
  });

  it("keeps the channel and reports the backend's reason when an unlink fails", async () => {
    api.fetchMumaJson.mockResolvedValueOnce([TRAXTORM]);
    const { onmessage, onerror } = show({ canManage: true, canUnlink: true });
    const button = await screen.findByTestId("label-channel-unlink");
    api.fetchMumaJson.mockRejectedValueOnce(
      Object.assign(new Error("403"), { body: { detail: "Missing permission: rules.manage" } }),
    );
    await fireEvent.click(button);
    await waitFor(() => expect(onerror).toHaveBeenCalledWith("Missing permission: rules.manage"));
    api.fetchMumaJson.mockRejectedValueOnce(new Error("offline"));
    await fireEvent.click(button);
    await waitFor(() =>
      expect(onerror).toHaveBeenLastCalledWith(expect.stringContaining("Traxtorm Records")),
    );
    expect(screen.getAllByTestId("label-channel")).toHaveLength(1);
    expect(onmessage).not.toHaveBeenCalled();
  });
});
