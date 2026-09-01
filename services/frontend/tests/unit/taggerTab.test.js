import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import TaggerTab from "../../src/lib/management/tabs/TaggerTab.svelte";

function props(overrides = {}) {
  return {
    API_BASE: "http://muma",
    getHeaders: (extra = {}) => ({ "x-api-key": "key", ...extra }),
    artistSearch: "",
    labelSearch: "",
    artists: [{ name: "Angerfist" }, { name: "Outsiders" }],
    labels: [{ name: "Roughstate" }],
    rules: { genres: [{ id: 1, name: "Hardcore", color: "#1ed760" }] },
    artistGenreRules: [{ id: 11, artist_name: "Angerfist", genre_name: "Hardcore", genre_id: 1 }],
    labelGenreRules: [{ id: 21, label_name: "Roughstate", genre_name: "Hardcore", genre_id: 1 }],
    fetchRules: vi.fn(),
    searchArtists: vi.fn(),
    searchLabels: vi.fn(),
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

/** Fill in an artist (or label) and a genre, so the add button becomes usable.
 *
 * The two name pickers are list boxes without their own label -- the visible
 * labels belong to the search inputs above them -- so they are addressed by
 * position: artist, label, genre.
 */
async function pick(container, { artist, label, genre = "1" }) {
  const [artistList, labelList, genreList] = container.querySelectorAll("select");
  if (artist) await fireEvent.change(artistList, { target: { value: artist } });
  if (label) await fireEvent.change(labelList, { target: { value: label } });
  await fireEvent.change(genreList, { target: { value: genre } });
}

describe("TaggerTab", () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("opens on the artists and labels sub tab", () => {
    const { container } = render(TaggerTab, props());

    expect(container.querySelectorAll("select")).toHaveLength(3);
    const [artistList, labelList] = container.querySelectorAll("select");
    expect([...artistList.options].map((option) => option.value)).toEqual([
      "Angerfist",
      "Outsiders",
    ]);
    expect([...labelList.options].map((option) => option.value)).toEqual(["Roughstate"]);
  });

  it("cannot add a rule before both halves are picked", () => {
    render(TaggerTab, props());

    expect(screen.getByText(/Koppel artiest/i).disabled).toBe(true);
    expect(screen.getByText(/Koppel label/i).disabled).toBe(true);
  });

  it("links an artist to a genre", async () => {
    const onMessage = vi.fn();
    const { container } = render(TaggerTab, props({ onMessage }));

    await pick(container, { artist: "Angerfist" });
    await fireEvent.click(screen.getByText(/Koppel artiest/i));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Regel toegevoegd voor Angerfist"));
    const [url, options] = actionCalls()[0];
    expect(url).toBe("http://muma/api/rules/artist-genres");
    expect(JSON.parse(options.body)).toEqual({ artist_name: "Angerfist", genre_id: 1 });
  });

  it("links a label to a genre", async () => {
    const onMessage = vi.fn();
    const { container } = render(TaggerTab, props({ onMessage }));

    await pick(container, { label: "Roughstate" });
    await fireEvent.click(screen.getByText(/Koppel label/i));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Regel toegevoegd voor Roughstate"));
    expect(actionCalls()[0][0]).toBe("http://muma/api/rules/label-genres");
  });

  it("reloads the rules after adding one", async () => {
    const fetchRules = vi.fn();
    const { container } = render(TaggerTab, props({ fetchRules }));

    await pick(container, { artist: "Angerfist" });
    await fireEvent.click(screen.getByText(/Koppel artiest/i));

    await waitFor(() => expect(fetchRules).toHaveBeenCalled());
  });

  it("a refused rule is not reported as added", async () => {
    globalThis.fetch = mockApi({ ok: false });
    const onMessage = vi.fn();
    const fetchRules = vi.fn();
    const { container } = render(TaggerTab, props({ onMessage, fetchRules }));

    await pick(container, { artist: "Angerfist" });
    await fireEvent.click(screen.getByText(/Koppel artiest/i));

    await waitFor(() => expect(actionCalls().length).toBeGreaterThan(0));
    expect(onMessage).not.toHaveBeenCalled();
    expect(fetchRules).not.toHaveBeenCalled();
  });

  it("reports an artist rule that never reached the server", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });
    const onError = vi.fn();
    const { container } = render(TaggerTab, props({ onError }));

    await pick(container, { artist: "Angerfist" });
    await fireEvent.click(screen.getByText(/Koppel artiest/i));

    await waitFor(() => expect(onError).toHaveBeenCalled());
  });

  it("reports a label rule that never reached the server", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });
    const onError = vi.fn();
    const { container } = render(TaggerTab, props({ onError }));

    await pick(container, { label: "Roughstate" });
    await fireEvent.click(screen.getByText(/Koppel label/i));

    await waitFor(() => expect(onError).toHaveBeenCalled());
  });

  it("lists the existing rules on the rules sub tab", async () => {
    render(TaggerTab, props());

    await fireEvent.click(screen.getByText("Genre Koppelingen"));

    expect(screen.getByText("Angerfist")).toBeTruthy();
    expect(screen.getByText("Roughstate")).toBeTruthy();
  });

  it("deletes an artist rule", async () => {
    const onMessage = vi.fn();
    render(TaggerTab, props({ onMessage }));
    await fireEvent.click(screen.getByText("Genre Koppelingen"));

    const [deleteArtistRule] = screen
      .getAllByRole("button")
      .filter((b) => b.className.includes("hover:text-red-500"));
    await fireEvent.click(deleteArtistRule);

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Regel verwijderd."));
    const [url, options] = actionCalls()[0];
    expect(url).toBe("http://muma/api/rules/artist-genres/11");
    expect(options.method).toBe("DELETE");
  });

  it("deletes a label rule", async () => {
    render(TaggerTab, props());
    await fireEvent.click(screen.getByText("Genre Koppelingen"));

    const buttons = screen
      .getAllByRole("button")
      .filter((b) => b.className.includes("hover:text-red-500"));
    await fireEvent.click(buttons[buttons.length - 1]);

    await waitFor(() => expect(actionCalls()[0][0]).toBe("http://muma/api/rules/label-genres/21"));
  });

  it("reports a delete that never reached the server", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });
    const onError = vi.fn();
    render(TaggerTab, props({ onError }));
    await fireEvent.click(screen.getByText("Genre Koppelingen"));

    const [deleteRule] = screen
      .getAllByRole("button")
      .filter((b) => b.className.includes("hover:text-red-500"));
    await fireEvent.click(deleteRule);

    await waitFor(() => expect(onError).toHaveBeenCalled());
  });

  it("shows the genre table on the genres sub tab", async () => {
    render(TaggerTab, props());

    await fireEvent.click(screen.getByText("Genre Overzicht"));

    expect(screen.getByText("Hardcore")).toBeTruthy();
    expect(screen.getByText("2 mappings")).toBeTruthy();
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

    it("starts the retag and clears the block", async () => {
      withPending({ total: 12, by_reason: [{ reason: "artist_genre_rule", count: 12 }] });
      const onMessage = vi.fn();

      render(TaggerTab, props({ onMessage }));

      await waitFor(() => expect(screen.getByTestId("retag-pending")).toBeTruthy());
      await fireEvent.click(screen.getByText("NU RETAGGEN"));

      await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Retag gestart."));
      expect(actionCalls()[0][0]).toBe("http://muma/api/tagger/retag/run");
      expect(screen.queryByTestId("retag-pending")).toBeNull();
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
