import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import NewsTab from "../../src/lib/management/tabs/NewsTab.svelte";

const SOURCE = {
  slug: "nos",
  name: "NOS Nieuws (NPO Radio 1)",
  stream_url: "https://icecast.omroep.nl/radio1-bb-mp3",
  minute_of_hour: 0,
  duration_seconds: 600,
  retention_count: 12,
  enabled: true,
  last_error: null,
  last_success_at: 1787248800,
};

const BULLETINS = [
  { id: 3, source: "nos", started_at: 1787248800, duration_ms: 612000, size_bytes: 14688000 },
];

function props(overrides = {}) {
  return {
    API_BASE: "http://muma",
    getHeaders: (extra = {}) => ({ "x-api-key": "key", ...extra }),
    onMessage: vi.fn(),
    onError: vi.fn(),
    ...overrides,
  };
}

function mockApi({
  source = SOURCE,
  bulletins = BULLETINS,
  recordResult = { started: true, slug: "nos", duration_seconds: 600 },
} = {}) {
  return vi.fn(async (url, options = {}) => {
    if (url.includes("/record-now")) {
      return { ok: true, json: async () => recordResult };
    }
    if (options.method && options.method !== "GET") {
      return { ok: true, json: async () => ({ slug: "nos" }) };
    }
    if (url.includes("/api/news/bulletins")) {
      return { ok: true, json: async () => ({ bulletins }) };
    }
    return { ok: true, json: async () => ({ sources: [source] }) };
  });
}

function writes() {
  return globalThis.fetch.mock.calls.filter(
    ([, options]) => options?.method && options.method !== "GET",
  );
}

describe("NewsTab", () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the configured source", async () => {
    render(NewsTab, props());
    await waitFor(() => expect(screen.getByDisplayValue("NOS Nieuws (NPO Radio 1)")).toBeTruthy());
    expect(screen.getByDisplayValue("https://icecast.omroep.nl/radio1-bb-mp3")).toBeTruthy();
    expect(screen.getByDisplayValue("600")).toBeTruthy();
  });

  it("lists the recordings that are still kept", async () => {
    render(NewsTab, props());
    await waitFor(() => expect(screen.getByText(/10:12/)).toBeTruthy());
  });

  it("saves the settings as a PUT on the source", async () => {
    render(NewsTab, props());
    await waitFor(() => expect(screen.getByDisplayValue("600")).toBeTruthy());
    await fireEvent.click(screen.getByRole("button", { name: /opslaan|save/i }));
    await waitFor(() => expect(writes().length).toBe(1));
    const [url, options] = writes()[0];
    expect(url).toBe("http://muma/api/news/sources/nos");
    expect(options.method).toBe("PUT");
    expect(JSON.parse(options.body).duration_seconds).toBe(600);
  });

  it("records on demand rather than waiting an hour", async () => {
    const onMessage = vi.fn();
    render(NewsTab, props({ onMessage }));
    await waitFor(() => expect(screen.getByDisplayValue("600")).toBeTruthy());
    await fireEvent.click(screen.getByRole("button", { name: /nu opnemen|record now/i }));
    await waitFor(() => expect(onMessage).toHaveBeenCalled());
    expect(globalThis.fetch.mock.calls.some(([url]) => url.includes("/record-now"))).toBe(true);
  });

  it("reports that the recording started, not that it finished", async () => {
    // The server records in the background: a ten-minute capture cannot be
    // awaited inside one request, so the screen must not claim it is done.
    const onMessage = vi.fn();
    render(NewsTab, props({ onMessage }));
    await waitFor(() => expect(screen.getByDisplayValue("600")).toBeTruthy());
    await fireEvent.click(screen.getByRole("button", { name: /nu opnemen|record now/i }));
    await waitFor(() => expect(onMessage).toHaveBeenCalled());
    expect(onMessage.mock.calls[0][0]).toMatch(/600/);
  });

  it("says so when the recording could not be started at all", async () => {
    globalThis.fetch = mockApi({ recordResult: { detail: "Unknown source" } });
    const onError = vi.fn();
    render(NewsTab, props({ onError }));
    await waitFor(() => expect(screen.getByDisplayValue("600")).toBeTruthy());
    await fireEvent.click(screen.getByRole("button", { name: /nu opnemen|record now/i }));
    await waitFor(() => expect(onError).toHaveBeenCalled());
  });

  it("refreshes the list, since a background capture cannot announce itself", async () => {
    render(NewsTab, props());
    await waitFor(() => expect(screen.getByDisplayValue("600")).toBeTruthy());
    const before = globalThis.fetch.mock.calls.length;
    await fireEvent.click(screen.getByRole("button", { name: /vernieuwen|refresh/i }));
    await waitFor(() => expect(globalThis.fetch.mock.calls.length).toBeGreaterThan(before));
  });
});
