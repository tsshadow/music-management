import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import { get } from "svelte/store";
import TaggerTab from "../../src/lib/management/tabs/TaggerTab.svelte";
import { activeManagementTab } from "../../src/lib/store.js";

function props(overrides = {}) {
  return {
    API_BASE: "http://muma",
    getHeaders: (extra = {}) => ({ "x-api-key": "key", ...extra }),
    onMessage: vi.fn(),
    onError: vi.fn(),
    ...overrides,
  };
}

function mockApi({ ok = true } = {}) {
  return vi.fn(async () => ({ ok, json: async () => ({}) }));
}

/** The calls the tab makes because someone clicked something.
 *
 * The tab also polls /api/tagger/retag/pending once on mount, which would otherwise
 * shift every index in these assertions by one.
 */
function actionCalls() {
  return globalThis.fetch.mock.calls.filter(([url]) => !String(url).includes("/retag/pending"));
}

describe("TaggerTab", () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("points at Curatie › Genres for the rules it no longer hosts", async () => {
    render(TaggerTab, props());

    expect(screen.getByText("Genreregels staan onder Curatie › Genres")).toBeTruthy();
    expect(screen.queryByText("Genre Overzicht")).toBeNull();
    expect(screen.queryByText("Genre Koppelingen")).toBeNull();

    await fireEvent.click(screen.getByText("Naar Genres"));

    expect(get(activeManagementTab)).toBe("genre-curation");
  });

  it("a full rescan asks for confirmation first", async () => {
    window.confirm.mockReturnValue(false);
    render(TaggerTab, props());

    await fireEvent.click(screen.getByText("FORCEER VOLLEDIGE RESCAN"));

    expect(actionCalls()).toHaveLength(0);
  });

  it("a confirmed rescan is triggered", async () => {
    const onMessage = vi.fn();
    render(TaggerTab, props({ onMessage }));

    await fireEvent.click(screen.getByText("FORCEER VOLLEDIGE RESCAN"));

    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith("Rescan voor alle bestanden getriggerd."),
    );
    expect(actionCalls()[0][0]).toBe("http://muma/api/tagger/rescan");
  });

  it("reports a rescan that never reached the server", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });
    const onError = vi.fn();
    render(TaggerTab, props({ onError }));

    await fireEvent.click(screen.getByText("FORCEER VOLLEDIGE RESCAN"));

    await waitFor(() => expect(onError).toHaveBeenCalled());
  });

  describe("the retag pile", () => {
    /** @param {object} pending what /api/tagger/retag/pending answers */
    function withPending(pending) {
      globalThis.fetch = vi.fn(async (url) => ({
        ok: true,
        status: 200,
        json: async () => (String(url).includes("/retag/pending") ? pending : {}),
      }));
    }

    it("shows the waiting files with the reason that queued them", async () => {
      withPending({ total: 142, by_reason: [{ reason: "genre_decision", count: 142 }] });

      render(TaggerTab, props());

      await waitFor(() => expect(screen.getByTestId("retag-pending")).toBeTruthy());
      expect(screen.getByText("142")).toBeTruthy();
      expect(screen.getByText(/genre_decision \(142\)/)).toBeTruthy();
    });

    it("hides the block when nothing is waiting", async () => {
      withPending({ total: 0, by_reason: [] });

      render(TaggerTab, props());

      await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
      expect(screen.queryByTestId("retag-pending")).toBeNull();
    });

    it("starts the retag and keeps the count on screen", async () => {
      // The count is the progress bar: it drops as the queue is worked off, so it
      // must not vanish the moment the button is pressed.
      withPending({ total: 12, by_reason: [{ reason: "artist_genre_rule", count: 12 }] });
      const onMessage = vi.fn();

      render(TaggerTab, props({ onMessage }));

      await waitFor(() => expect(screen.getByTestId("retag-pending")).toBeTruthy());
      await fireEvent.click(screen.getByText("NU RETAGGEN"));

      await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Retag gestart."));
      expect(actionCalls()[0][0]).toBe("http://muma/api/tagger/retag/run");
      expect(screen.getByTestId("retag-pending")).toBeTruthy();
      expect(screen.getByText("12")).toBeTruthy();
    });

    it("polls the count while the page is open", async () => {
      vi.useFakeTimers();
      try {
        withPending({ total: 12, by_reason: [] });
        render(TaggerTab, props());
        const before = globalThis.fetch.mock.calls.length;

        await vi.advanceTimersByTimeAsync(5000);

        expect(globalThis.fetch.mock.calls.length).toBe(before + 1);
      } finally {
        vi.useRealTimers();
      }
    });

    it("says so when the tagger is already running", async () => {
      const onError = vi.fn();
      globalThis.fetch = vi.fn(async (url) => {
        if (String(url).includes("/retag/pending")) {
          return { ok: true, status: 200, json: async () => ({ total: 3, by_reason: [] }) };
        }
        return { ok: false, status: 409, json: async () => ({}) };
      });

      render(TaggerTab, props({ onError }));

      await waitFor(() => expect(screen.getByTestId("retag-pending")).toBeTruthy());
      await fireEvent.click(screen.getByText("NU RETAGGEN"));

      await waitFor(() => expect(onError).toHaveBeenCalledWith("De tagger is al bezig."));
      expect(screen.getByTestId("retag-pending")).toBeTruthy();
    });

    it("shows stop and start-over instead of retag while a round runs", async () => {
      withPending({ total: 40, by_reason: [], busy: true, stopping: false });

      render(TaggerTab, props());

      await waitFor(() => expect(screen.getByTestId("tagger-state")).toBeTruthy());
      expect(screen.getByText("STOP")).toBeTruthy();
      expect(screen.getByText("OPNIEUW VAN VOREN")).toBeTruthy();
      expect(screen.queryByText("NU RETAGGEN")).toBeNull();
    });

    it("is visible for a walk with an empty queue, so it can be stopped", async () => {
      withPending({ total: 0, by_reason: [], busy: true, stopping: false });

      render(TaggerTab, props());

      await waitFor(() => expect(screen.getByTestId("retag-pending")).toBeTruthy());
      expect(screen.getByText("STOP")).toBeTruthy();
    });

    it("a stop is sent to the tagger", async () => {
      withPending({ total: 40, by_reason: [], busy: true, stopping: false });
      const onMessage = vi.fn();

      render(TaggerTab, props({ onMessage }));

      await waitFor(() => expect(screen.getByText("STOP")).toBeTruthy());
      await fireEvent.click(screen.getByText("STOP"));

      await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Stopverzoek verstuurd."));
      expect(actionCalls()[0][0]).toBe("http://muma/api/tagger/tag/stop");
      expect(actionCalls()[0][1].method).toBe("POST");
    });

    it("a start-over asks for the restart, not a plain run", async () => {
      withPending({ total: 40, by_reason: [], busy: true, stopping: false });
      const onMessage = vi.fn();

      render(TaggerTab, props({ onMessage }));

      await waitFor(() => expect(screen.getByText("OPNIEUW VAN VOREN")).toBeTruthy());
      await fireEvent.click(screen.getByText("OPNIEUW VAN VOREN"));

      await waitFor(() => expect(onMessage).toHaveBeenCalled());
      expect(actionCalls()[0][0]).toBe("http://muma/api/tagger/retag/restart");
    });

    it("disables both buttons once a stop is under way", async () => {
      withPending({ total: 40, by_reason: [], busy: true, stopping: true });

      render(TaggerTab, props());

      await waitFor(() => expect(screen.getByTestId("tagger-state")).toBeTruthy());
      expect(screen.getByTestId("tagger-state").textContent).toContain("stopt");
      expect(screen.getByText("STOP").closest("button").disabled).toBe(true);
      expect(screen.getByText("OPNIEUW VAN VOREN").closest("button").disabled).toBe(true);
    });

    it("stays hidden when the count cannot be fetched", async () => {
      globalThis.fetch = vi.fn(async () => {
        throw new Error("network down");
      });

      render(TaggerTab, props());

      await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
      expect(screen.queryByTestId("retag-pending")).toBeNull();
    });
  });
});
