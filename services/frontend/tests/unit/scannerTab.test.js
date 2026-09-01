import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import ScannerTab from "../../src/lib/management/tabs/ScannerTab.svelte";
import { credentials } from "../../src/lib/store.js";

const SCAN_SETTINGS = {
  updatePeriod: 1,
  updateStartTime: "05:00:00",
  similarityEngineType: 0,
  skipSingleReleasePlayLists: true,
  allowMBIDArtistMerge: false,
  artistImageFallbackToRelease: true,
  extraTagsToScan: { value: ["MOOD", "BPM"] },
  artistTagDelimiters: { value: [";"] },
  defaultTagDelimiters: { value: [] },
  artistsToNotSplit: { value: ["AC/DC"] },
};

function scanStatus(overrides = {}) {
  return {
    scanning: false,
    lastScan: {
      startTime: "2026-01-01T01:00:00Z",
      stopTime: "2026-01-01T01:00:30Z",
      count: 42,
      errors: 0,
    },
    scanSettings: SCAN_SETTINGS,
    ...overrides,
  };
}

function mockScanApi(status = scanStatus()) {
  return vi.fn(async () => ({
    ok: true,
    json: async () => ({ "subsonic-response": { status: "ok", scanStatus: status } }),
  }));
}

function props(overrides = {}) {
  return { onMessage: () => {}, onError: () => {}, ...overrides };
}

describe("ScannerTab", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user", password: "pw" });
    globalThis.fetch = mockScanApi();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the idle state with the last scan statistics", async () => {
    render(ScannerTab, props());

    await waitFor(() => expect(screen.getByText("Scanner inactief")).toBeTruthy());
    expect(screen.getByText("42")).toBeTruthy();
    expect(screen.getByText("30s")).toBeTruthy();
  });

  it("shows scan progress while a scan is running", async () => {
    globalThis.fetch = mockScanApi(
      scanStatus({
        scanning: true,
        step: "ScanFiles",
        stepIndex: 2,
        stepCount: 10,
        count: 500,
        totalCount: 1000,
      }),
    );

    render(ScannerTab, props());

    await waitFor(() => expect(screen.getByText("Bestanden scannen")).toBeTruthy());
    expect(screen.getByText(/Stap 3 van 10/)).toBeTruthy();
  });

  it("passes the selected scan options to startScan", async () => {
    render(ScannerTab, props());

    await waitFor(() => expect(screen.getByText("Scanner inactief")).toBeTruthy());

    await fireEvent.click(screen.getByLabelText("Volledige scan"));
    await fireEvent.click(screen.getByLabelText("Database compacteren"));
    await fireEvent.click(screen.getByText("Scan starten"));

    await waitFor(() => {
      const called = globalThis.fetch.mock.calls.map((c) => c[0]);
      const startCall = called.find((url) => url.includes("/rest/startScan"));
      expect(startCall).toBeTruthy();
      expect(startCall).toContain("fullScan=true");
      expect(startCall).toContain("compact=true");
      // Not ticked, so it must not be sent at all.
      expect(startCall).not.toContain("forceOptimize");
    });
  });

  it("normalizes Subsonic array nodes into editable tag lists", async () => {
    render(ScannerTab, props());

    await waitFor(() => expect(screen.getByDisplayValue("MOOD")).toBeTruthy());
    expect(screen.getByDisplayValue("BPM")).toBeTruthy();
    expect(screen.getByDisplayValue("AC/DC")).toBeTruthy();
  });

  it("saves the settings as pipe-separated lists", async () => {
    render(ScannerTab, props());

    await waitFor(() => expect(screen.getByDisplayValue("MOOD")).toBeTruthy());

    await fireEvent.click(screen.getByLabelText("Artiesten samenvoegen op MBID"));
    await fireEvent.click(screen.getByText("Opslaan"));

    await waitFor(() => {
      const saveCall = globalThis.fetch.mock.calls
        .map((c) => c[0])
        .find((url) => url.includes("/rest/updateScanSettings"));
      expect(saveCall).toBeTruthy();
      expect(saveCall).toContain("allowMBIDArtistMerge=true");
      expect(saveCall).toContain(`extraTagsToScan=${encodeURIComponent("MOOD|BPM")}`);
    });
  });

  it("explains itself instead of silently failing without server credentials", async () => {
    // Google sign-in users are admins in MuMa but have no Subsonic credentials,
    // so every /rest call would come back unauthorized.
    credentials.set({ url: "", username: "", password: "" });

    render(ScannerTab, props());

    await waitFor(() => expect(screen.getByText("Geen serververbinding")).toBeTruthy());
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });
});
