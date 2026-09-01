import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import DownloadersTab from "../../src/lib/management/tabs/DownloadersTab.svelte";

const SOUNDCLOUD_FIELDS = [
  {
    key: "sweep_interval",
    value: 900,
    default: 900,
    minimum: 60,
    maximum: 604800,
    unit: "seconden",
    description: "Hoe lang de worker wacht tussen twee rondes.",
  },
  {
    key: "retry_attempts",
    value: 3,
    default: 3,
    minimum: 1,
    maximum: 10,
    unit: "pogingen",
    description: "Aantal pogingen per account.",
  },
];

const RATE_STATE = {
  source: "soundcloud",
  multiplier: 1,
  clean_runs: 0,
  consecutive_403: 0,
  consecutive_429: 0,
  last_403_at: null,
  last_429_at: null,
  cooldown_until: null,
  cooldown_remaining: 0,
  effective_sweep_interval: 900,
  effective_account_cooldown: 21600,
};

function baseProps(overrides = {}) {
  return {
    API_BASE: "/muma",
    getHeaders: (extra = {}) => ({ ...extra, "X-API-Key": "k" }),
    accounts: [],
    youtubeAccounts: [],
    onMessage: () => {},
    onError: () => {},
    refreshDownloaders: () => {},
    ...overrides,
  };
}

/** A server that remembers what was posted, so a save can be read back. */
function mockApi() {
  const stored = {};
  const posts = [];
  const fetchMock = vi.fn(async (url, options = {}) => {
    if (url.endsWith("/api/downloaders/settings") && options.method === "POST") {
      const body = JSON.parse(options.body);
      posts.push(body);
      Object.assign(stored, body.updates);
      return { ok: true, status: 200, json: async () => ({ status: "success" }) };
    }
    if (url.endsWith("/api/downloaders/settings")) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          sources: [
            {
              source: "soundcloud",
              fields: SOUNDCLOUD_FIELDS.map((f) => ({ ...f, value: stored[f.key] ?? f.value })),
            },
          ],
        }),
      };
    }
    if (url.endsWith("/api/downloaders/rate-state")) {
      return { ok: true, status: 200, json: async () => ({ sources: [RATE_STATE] }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  });
  return { fetchMock, posts, stored };
}

async function openTimingTab() {
  await fireEvent.click(screen.getByRole("button", { name: "Timing" }));
  await waitFor(() => expect(screen.getByLabelText("sweep interval")).toBeTruthy());
}

describe("DownloadersTab timing settings", () => {
  let api;

  beforeEach(() => {
    api = mockApi();
    globalThis.fetch = api.fetchMock;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("sends an edited knob to the API when saving", async () => {
    render(DownloadersTab, baseProps());
    await openTimingTab();

    await fireEvent.input(screen.getByLabelText("sweep interval"), { target: { value: "1800" } });
    await fireEvent.click(screen.getByRole("button", { name: "OPSLAAN" }));

    await waitFor(() => expect(api.posts.length).toBe(1));
    expect(api.posts[0]).toEqual({ source: "soundcloud", updates: { sweep_interval: 1800 } });
  });

  it("shows the saved value after the reload, not the old one", async () => {
    render(DownloadersTab, baseProps());
    await openTimingTab();

    await fireEvent.input(screen.getByLabelText("sweep interval"), { target: { value: "1800" } });
    await fireEvent.click(screen.getByRole("button", { name: "OPSLAAN" }));

    await waitFor(() => expect(screen.getByLabelText("sweep interval").value).toBe("1800"));
  });

  it("names the reason on screen when the settings cannot be loaded", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 503,
      json: async () => ({ detail: "Could not read the downloader settings: Connection refused" }),
    }));
    render(DownloadersTab, baseProps());

    await fireEvent.click(screen.getByRole("button", { name: "Timing" }));

    // A blank pane with no save button is what "de settings worden niet opgeslagen"
    // actually looks like from the outside, so the reason has to stay on screen.
    await waitFor(() => expect(screen.getByText(/Connection refused/)).toBeTruthy());
  });

  it("offers a retry that loads the settings once the API is back", async () => {
    const failing = vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) }));
    globalThis.fetch = failing;
    render(DownloadersTab, baseProps());

    await fireEvent.click(screen.getByRole("button", { name: "Timing" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Opnieuw proberen" })).toBeTruthy(),
    );

    globalThis.fetch = api.fetchMock;
    await fireEvent.click(screen.getByRole("button", { name: "Opnieuw proberen" }));

    await waitFor(() => expect(screen.getByLabelText("sweep interval")).toBeTruthy());
  });

  it("clears the error once the settings load", async () => {
    const failing = vi.fn(async () => ({ ok: false, status: 503, json: async () => ({}) }));
    globalThis.fetch = failing;
    render(DownloadersTab, baseProps());

    await fireEvent.click(screen.getByRole("button", { name: "Timing" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Opnieuw proberen" })).toBeTruthy(),
    );

    globalThis.fetch = api.fetchMock;
    await fireEvent.click(screen.getByRole("button", { name: "Opnieuw proberen" }));

    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Opnieuw proberen" })).toBeNull(),
    );
  });

  it("reports the API detail when a save is refused", async () => {
    render(DownloadersTab, baseProps());
    await openTimingTab();

    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 503,
      json: async () => ({ detail: "Could not store the downloader settings: Connection refused" }),
    }));
    await fireEvent.input(screen.getByLabelText("sweep interval"), { target: { value: "1800" } });
    await fireEvent.click(screen.getByRole("button", { name: "OPSLAAN" }));

    await waitFor(() => expect(screen.getByText(/Connection refused/)).toBeTruthy());
  });

  it("leaves untouched knobs out of the payload", async () => {
    render(DownloadersTab, baseProps());
    await openTimingTab();

    await fireEvent.input(screen.getByLabelText("retry attempts"), { target: { value: "5" } });
    await fireEvent.click(screen.getByRole("button", { name: "OPSLAAN" }));

    await waitFor(() => expect(api.posts.length).toBe(1));
    expect(api.posts[0].updates).toEqual({ retry_attempts: 5 });
  });
});
