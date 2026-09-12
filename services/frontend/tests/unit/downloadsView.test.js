import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/svelte";
import { get } from "svelte/store";
import DownloadsView from "../../src/lib/DownloadsView.svelte";
import { currentTrack, playlist } from "../../src/lib/store.js";

const TRACK = {
  id: "1",
  title: "Incoming",
  artist: "Angerfist",
  album: "Close Combat",
  duration: 210,
  state: "done",
};
const SET = {
  id: "2",
  title: "Defqon.1 2024",
  artist: "Angerfist",
  album: "Close Combat",
  duration: 5400,
  state: "running",
};

/**
 * A shell whose storage answers with `items` and `bytes`.
 *
 * @param {object} [options]
 * @returns {object}
 */
function shell({ items = [TRACK, SET], bytes = 1_240_000_000, ...rest } = {}) {
  const handlers = [];
  return {
    emit: (event) => handlers.forEach((handler) => handler(event)),
    storage: {
      supported: true,
      list: vi.fn(async () => items),
      size: vi.fn(async () => bytes),
      remove: vi.fn(async () => {}),
      download: vi.fn(async () => ({ requested: 1, unknown: 0 })),
      onProgress: vi.fn((handler) => {
        handlers.push(handler);
        return () => {};
      }),
      ...rest,
    },
  };
}

describe("DownloadsView", () => {
  beforeEach(() => {
    playlist.set([]);
    currentTrack.set(null);
  });

  afterEach(() => vi.restoreAllMocks());

  it("groups an album's tracks and gives a set a row of its own", async () => {
    render(DownloadsView, { platform: shell() });

    await waitFor(() => expect(screen.getAllByTestId("download-group")).toHaveLength(2));
    expect(screen.getByText("Close Combat")).toBeTruthy();
    expect(screen.getByText(/Defqon\.1 2024/)).toBeTruthy();
  });

  it("heads the page with the total the device reports", async () => {
    render(DownloadsView, { platform: shell() });

    await waitFor(() =>
      expect(screen.getByTestId("downloads-total").textContent).toMatch(/1,2 GB/),
    );
  });

  it("names the state of every group", async () => {
    render(DownloadsView, { platform: shell() });

    await waitFor(() => expect(screen.getByTitle("Gedownload")).toBeTruthy());
    expect(screen.getByTitle("Bezig met downloaden")).toBeTruthy();
  });

  it("says a size is estimated, because `list()` reports no byte count at all", async () => {
    render(DownloadsView, { platform: shell() });

    await waitFor(() =>
      expect(screen.getByText(/geschat uit de bitrate en de lengte/i)).toBeTruthy(),
    );
  });

  it("asks before removing, and then removes every id in the group", async () => {
    const platform = shell({ items: [TRACK] });
    render(DownloadsView, { platform });

    await waitFor(() => expect(screen.getByTitle("Download verwijderen")).toBeTruthy());
    await fireEvent.click(screen.getByTitle("Download verwijderen"));

    const confirm = screen.getByTestId("remove-confirm");
    await fireEvent.click(within(confirm).getByRole("button", { name: "Download verwijderen" }));

    await waitFor(() => expect(platform.storage.remove).toHaveBeenCalledWith(["1"]));
  });

  it("lets the confirmation be waved away without removing anything", async () => {
    const platform = shell({ items: [TRACK] });
    render(DownloadsView, { platform });

    await waitFor(() => expect(screen.getByTitle("Download verwijderen")).toBeTruthy());
    await fireEvent.click(screen.getByTitle("Download verwijderen"));
    await fireEvent.click(screen.getByRole("button", { name: "Annuleren" }));

    expect(screen.queryByTestId("remove-confirm")).toBeNull();
    expect(platform.storage.remove).not.toHaveBeenCalled();
  });

  it("follows the progress event without re-reading the list", async () => {
    const platform = shell({ items: [{ ...TRACK, state: "queued" }] });
    render(DownloadsView, { platform });

    await waitFor(() => expect(screen.getByTitle("In de wachtrij")).toBeTruthy());
    platform.emit({ id: "1", state: "running", progress: 40 });

    await waitFor(() => expect(screen.getByTitle("Bezig met downloaden")).toBeTruthy());
    expect(platform.storage.list).toHaveBeenCalledOnce();
  });

  it("re-reads the total once a download actually finished", async () => {
    const platform = shell({ items: [{ ...TRACK, state: "running" }] });
    render(DownloadsView, { platform });

    await waitFor(() => expect(platform.storage.size).toHaveBeenCalledOnce());
    platform.emit({ id: "1", state: "done", progress: 100 });

    await waitFor(() => expect(platform.storage.size).toHaveBeenCalledTimes(2));
  });

  it("plays a group from its first item", async () => {
    render(DownloadsView, { platform: shell({ items: [TRACK] }) });

    await waitFor(() => expect(screen.getByText("Close Combat")).toBeTruthy());
    await fireEvent.click(screen.getByText("Close Combat"));

    expect(get(playlist)).toHaveLength(1);
    expect(get(currentTrack).id).toBe("1");
  });

  it("offers a retry on a group that failed", async () => {
    const platform = shell({ items: [{ ...TRACK, state: "failed" }] });
    render(DownloadsView, { platform });

    await waitFor(() => expect(screen.getByText("Opnieuw proberen")).toBeTruthy());
    await fireEvent.click(screen.getByText("Opnieuw proberen"));

    expect(platform.storage.download).toHaveBeenCalledWith(["1"], { pin: true });
  });

  it("says nothing is downloaded rather than showing an empty list", async () => {
    render(DownloadsView, { platform: shell({ items: [], bytes: 0 }) });

    await waitFor(() => expect(screen.getByText("Geen downloads")).toBeTruthy());
  });

  // Acceptance criterion 13: the tab is not listed in a browser, and landing on
  // the route anyway must not read as "my downloads are gone".
  it("explains itself in a browser instead of looking empty", async () => {
    const platform = { storage: { supported: false } };

    render(DownloadsView, { platform });

    await waitFor(() => expect(screen.getByText("Downloads zitten in de app")).toBeTruthy());
    expect(screen.queryByTestId("downloads-total")).toBeNull();
  });
});
