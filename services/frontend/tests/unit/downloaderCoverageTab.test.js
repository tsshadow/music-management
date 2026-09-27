import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import DownloaderCoverage from "../../src/lib/management/DownloaderCoverage.svelte";

const RATE_STATE = {
  source: "soundcloud",
  multiplier: 1,
  cooldown_remaining: 0,
};

function body(source = "soundcloud") {
  return {
    source,
    generated_at: "2026-09-21T12:00:00",
    totals: {
      configured: 3,
      counted: 2,
      complete: 1,
      with_backlog: 1,
      never_counted: 1,
      listed: 1130,
      held: 1030,
      excluded: 10,
      remaining: 90,
      downloads_7d: 12,
      downloads_30d: 80,
      write_offs: [
        { reason: "too_short", count: 4 },
        { reason: "failing", count: 0 },
      ],
      rate_state: RATE_STATE,
    },
    accounts: [
      {
        account: "dirty-workz",
        key: "dirty-workz",
        download_type: null,
        listed: 1030,
        held: 940,
        excluded: 0,
        remaining: 90,
        coverage: 0.9126,
        state: "capped",
        snapshot_at: "2026-09-20T12:00:00",
        last_checked_at: "2026-09-21T10:00:00",
        last_deep_sweep_at: null,
        last_download_at: null,
        channel: {
          id: 7,
          name: "Dirty Workz",
          label: { id: 3, name: "Dirty Workz" },
          artist: null,
          open_proposals: 1,
        },
      },
      {
        account: "done-records",
        key: "done-records",
        download_type: null,
        listed: 100,
        held: 90,
        excluded: 10,
        remaining: 0,
        coverage: 0.9,
        state: "complete",
        snapshot_at: "2026-09-19T12:00:00",
        last_checked_at: "2026-09-21T10:00:00",
        last_deep_sweep_at: "2026-09-19T12:00:00",
        last_download_at: "2026-09-18T12:00:00",
      },
      {
        account: "fresh-face",
        key: "fresh-face",
        download_type: null,
        listed: null,
        held: null,
        excluded: null,
        remaining: null,
        coverage: null,
        state: null,
        snapshot_at: null,
        last_checked_at: null,
        last_deep_sweep_at: null,
        last_download_at: null,
      },
    ],
  };
}

function props() {
  return {
    API_BASE: "/muma",
    getHeaders: (extra = {}) => ({ ...extra, "X-API-Key": "k" }),
  };
}

describe("DownloaderCoverage", () => {
  let requested;

  beforeEach(() => {
    requested = [];
    globalThis.fetch = vi.fn(async (url) => {
      requested.push(url);
      const source = url.endsWith("/youtube") ? "youtube" : "soundcloud";
      return { ok: true, status: 200, json: async () => body(source) };
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the tiles from the totals", async () => {
    render(DownloaderCoverage, props());
    await waitFor(() => expect(screen.getByText("Geteld")).toBeTruthy());
    expect(screen.getByText("1 nog niet geteld")).toBeTruthy();
    expect(screen.getByText("1 met achterstand")).toBeTruthy();
    expect(screen.getByText("1.030 van 1.130 gearchiveerd")).toBeTruthy();
    expect(screen.getByText("80 in de laatste 30 dagen")).toBeTruthy();
    expect(screen.getByText("te kort")).toBeTruthy();
  });

  it("lists only the channels with a backlog by default, biggest first", async () => {
    render(DownloaderCoverage, props());
    await waitFor(() => expect(screen.getByText("dirty-workz")).toBeTruthy());
    expect(screen.queryByText("done-records")).toBeNull();
    expect(screen.queryByText("fresh-face")).toBeNull();
    expect(screen.getByText("1 van 1 kanalen")).toBeTruthy();
  });

  it("says a channel without a snapshot is not counted yet, and an unknown last download is unknown", async () => {
    render(DownloaderCoverage, props());
    await waitFor(() => expect(screen.getByText("dirty-workz")).toBeTruthy());
    await fireEvent.change(screen.getByLabelText("Filter"), {
      target: { value: "all" },
    });
    await waitFor(() => expect(screen.getByText("fresh-face")).toBeTruthy());
    // The uncounted row says so in both the progress and the count column.
    expect(screen.getAllByText("nog niet geteld").length).toBeGreaterThanOrEqual(2);
    // dirty-workz has no archive row with a timestamp; fresh-face has none at all.
    expect(screen.getAllByText("onbekend").length).toBe(2);
    expect(screen.getByText("3 van 3 kanalen")).toBeTruthy();
  });

  it("shows the bar as held over listed with the percentage", async () => {
    render(DownloaderCoverage, props());
    await waitFor(() => expect(screen.getByText("dirty-workz")).toBeTruthy());
    expect(screen.getByText("940")).toBeTruthy();
    expect(screen.getByText(/\/ 1\.030 · 91%/)).toBeTruthy();
    expect(screen.getByText(/afgekapt op het maximum/)).toBeTruthy();
  });

  it("fetches the other source when switched and does not refetch when switched back", async () => {
    render(DownloaderCoverage, props());
    await waitFor(() => expect(requested.length).toBe(1));
    await fireEvent.click(screen.getByRole("button", { name: "YouTube" }));
    await waitFor(() => expect(requested.length).toBe(2));
    expect(requested[1]).toBe("/muma/api/downloaders/coverage/youtube");
    await fireEvent.click(screen.getByRole("button", { name: "SoundCloud" }));
    await waitFor(() => expect(screen.getByText("dirty-workz")).toBeTruthy());
    expect(requested.length).toBe(2);
  });

  it("shows the label a channel is linked to and a marker for an open proposal", async () => {
    const onOpenLinks = vi.fn();
    render(DownloaderCoverage, { ...props(), onOpenLinks });
    await waitFor(() => expect(screen.getByText("dirty-workz")).toBeTruthy());
    expect(screen.getByText("Gekoppeld aan")).toBeTruthy();
    expect(screen.getByText("Dirty Workz")).toBeTruthy();
    await fireEvent.click(screen.getByRole("button", { name: "voorstel" }));
    expect(onOpenLinks).toHaveBeenCalled();
  });

  it("offers a hand link for a channel with no link and no proposal, passing the channel on", async () => {
    const unlinked = { id: 7, name: "Dirty Workz", label: null, artist: null, open_proposals: 0 };
    globalThis.fetch = vi.fn(async () => {
      const data = body();
      data.accounts[0].channel = unlinked;
      return { ok: true, status: 200, json: async () => data };
    });
    const onOpenLinks = vi.fn();
    render(DownloaderCoverage, { ...props(), onOpenLinks });
    await waitFor(() => expect(screen.getByText("dirty-workz")).toBeTruthy());
    expect(screen.queryByRole("button", { name: "voorstel" })).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "koppelen" }));
    expect(onOpenLinks).toHaveBeenCalledWith(unlinked);
  });

  it("unlinks through the channel-links endpoint and reloads", async () => {
    render(DownloaderCoverage, props());
    await waitFor(() => expect(screen.getByText("Dirty Workz")).toBeTruthy());
    await fireEvent.click(screen.getByRole("button", { name: "Dirty Workz ontkoppelen" }));
    await waitFor(() => expect(requested).toContain("/muma/api/channel-links/channels/7/label"));
    await waitFor(() => expect(requested.length).toBe(3));
  });

  it("names the reason on screen when the counts cannot be loaded", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 503,
      json: async () => ({
        detail: "Could not read the coverage: Connection refused",
      }),
    }));
    render(DownloaderCoverage, props());
    await waitFor(() => expect(screen.getByText(/Connection refused/)).toBeTruthy());
  });
});
