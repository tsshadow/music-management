import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import RadioTab from "../../src/lib/management/tabs/RadioTab.svelte";

const CHANNELS = [
  { slug: "main", name: "Radio", enabled: true, filter: {} },
  {
    slug: "qdance",
    name: "Q-dance",
    enabled: false,
    filter: { label: "Q-dance Records", rating_min: 4 },
  },
];

const LABELS = [
  { id: 1, name: "Q-dance Records" },
  { id: 2, name: "Dirty Workz" },
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

/** Answers the channel list, the label suggestions, and any write. */
function mockApi({ channels = CHANNELS, writeOk = true, detail = "Nope", preview = null } = {}) {
  return vi.fn(async (url, options = {}) => {
    if (url.includes("/channels/preview")) {
      return {
        ok: preview !== null,
        json: async () => preview ?? { detail },
      };
    }
    if (options.method && options.method !== "GET") {
      return { ok: writeOk, json: async () => ({ detail }) };
    }
    if (url.includes("/api/labels")) return { ok: true, json: async () => LABELS };
    return { ok: true, json: async () => ({ channels }) };
  });
}

async function renderLoaded(overrides = {}) {
  const rendered = render(RadioTab, props(overrides));
  await waitFor(() => expect(screen.getByText("Q-dance")).toBeTruthy());
  return rendered;
}

function writes() {
  return globalThis.fetch.mock.calls.filter(
    ([, options]) => options?.method && options.method !== "GET",
  );
}

describe("RadioTab", () => {
  beforeEach(() => {
    globalThis.fetch = mockApi();
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists channels that are off the air too, since only an editor sees this screen", async () => {
    await renderLoaded();

    const urls = globalThis.fetch.mock.calls.map(([url]) => url);
    expect(urls.some((url) => url.includes("include_disabled=true"))).toBe(true);
  });

  it("says what each channel plays", async () => {
    await renderLoaded();

    expect(screen.getByText("Q-dance Records · 4★+")).toBeTruthy();
    expect(screen.getByText("De hele bibliotheek")).toBeTruthy();
  });

  it("creates a channel from what was filled in, with a slug derived from the name", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText("Nieuw kanaal"));
    await fireEvent.input(screen.getByLabelText("Naam"), { target: { value: "Dirty Workz" } });
    await fireEvent.input(screen.getByLabelText("Label"), { target: { value: "Dirty Workz" } });
    await fireEvent.click(screen.getByText("Opslaan"));

    await waitFor(() => expect(writes().length).toBe(1));
    const [url, options] = writes()[0];
    expect(url).toBe("http://muma/api/radio/channels");
    expect(options.method).toBe("POST");
    expect(JSON.parse(options.body)).toEqual({
      slug: "dirty-workz",
      name: "Dirty Workz",
      filter: { label: "Dirty Workz" },
    });
  });

  it("refuses to save a channel without a name", async () => {
    const onError = vi.fn();
    await renderLoaded({ onError });

    await fireEvent.click(screen.getByText("Nieuw kanaal"));
    await fireEvent.click(screen.getByText("Opslaan"));

    expect(writes().length).toBe(0);
    expect(onError).toHaveBeenCalled();
  });

  it("edits an existing channel by slug rather than creating a second one", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getAllByText("Bewerken")[1]);
    await fireEvent.input(screen.getByLabelText("Naam"), { target: { value: "Q-dance Radio" } });
    await fireEvent.click(screen.getByText("Opslaan"));

    await waitFor(() => expect(writes().length).toBe(1));
    const [url, options] = writes()[0];
    expect(url).toBe("http://muma/api/radio/channels/qdance");
    expect(options.method).toBe("PUT");
    expect(JSON.parse(options.body).filter).toEqual({ label: "Q-dance Records", rating_min: 4 });
  });

  it("takes a channel off the air without touching its filter", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText("Uit de lucht halen"));

    await waitFor(() => expect(writes().length).toBe(1));
    expect(JSON.parse(writes()[0][1].body)).toEqual({ enabled: false });
  });

  it("previews a filter before it is saved", async () => {
    globalThis.fetch = mockApi({
      preview: {
        matched: 42,
        truncated: false,
        sample: [{ track_id: "tr-1", artist: "A", title: "T" }],
      },
    });
    await renderLoaded();

    await fireEvent.click(screen.getAllByText("Bewerken")[1]);
    await fireEvent.click(screen.getByText("Proefdraaien"));

    await waitFor(() => expect(screen.getByText("42 tracks passen hierbij.")).toBeTruthy());
    expect(screen.getByText("A — T")).toBeTruthy();
  });

  it("reports a filter LMS cannot answer instead of saving it blind", async () => {
    const onError = vi.fn();
    globalThis.fetch = mockApi({ detail: "LMS could not answer this filter" });
    await renderLoaded({ onError });

    await fireEvent.click(screen.getAllByText("Bewerken")[1]);
    await fireEvent.click(screen.getByText("Proefdraaien"));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("LMS could not answer this filter"));
  });

  it("confirms before deleting a channel", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getAllByLabelText("Verwijderen")[0]);

    await waitFor(() => expect(writes().length).toBe(1));
    expect(window.confirm).toHaveBeenCalled();
    expect(writes()[0][1].method).toBe("DELETE");
  });
});
