import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import RadioStationsSection from "../../src/lib/management/tabs/RadioStationsSection.svelte";

const SLAM = {
  slug: "slam",
  name: "SLAM",
  stream_url: "https://example.com/slam.mp3",
  sort_order: 10,
  enabled: true,
};
const OFF = { ...SLAM, slug: "off", name: "Off Air", sort_order: 20, enabled: false };

function props() {
  return {
    API_BASE: "http://muma",
    getHeaders: (extra = {}) => ({ "x-api-key": "key", ...extra }),
    onMessage: vi.fn(),
    onError: vi.fn(),
  };
}

/** Answers the list and any write, and keeps the write for the assertion. */
function mockApi({ writeOk = true, detail = "Nope" } = {}) {
  return vi.fn(async (url, options = {}) => {
    if (options.method) return { ok: writeOk, json: async () => ({ detail }) };
    return { ok: true, json: async () => ({ stations: [SLAM, OFF] }) };
  });
}

function write(method) {
  return globalThis.fetch.mock.calls.find(([, options]) => options?.method === method);
}

describe("RadioStationsSection", () => {
  const realFetch = globalThis.fetch;

  beforeEach(() => {
    globalThis.fetch = mockApi();
  });

  afterEach(() => {
    globalThis.fetch = realFetch;
    vi.restoreAllMocks();
  });

  async function renderLoaded(given = props()) {
    render(RadioStationsSection, given);
    await waitFor(() => expect(screen.getByText("SLAM")).toBeTruthy());
    return given;
  }

  it("lists stations that are off the air too", async () => {
    await renderLoaded();

    expect(screen.getByText("Off Air")).toBeTruthy();
    expect(globalThis.fetch.mock.calls[0][0]).toContain("include_disabled=true");
  });

  it("adds a station, with a slug made from the name", async () => {
    const given = await renderLoaded();

    await fireEvent.click(screen.getByText("Nieuwe zender"));
    await fireEvent.input(screen.getByLabelText("Naam"), { target: { value: "Radio 538" } });
    await fireEvent.input(screen.getByLabelText("Streamadres (https)"), {
      target: { value: "https://example.com/538.mp3" },
    });
    await fireEvent.click(screen.getByText("Opslaan"));

    await waitFor(() => expect(given.onMessage).toHaveBeenCalled());
    const [url, options] = write("POST");
    expect(url).toBe("http://muma/api/radio/stations");
    expect(JSON.parse(options.body)).toEqual({
      slug: "radio-538",
      name: "Radio 538",
      stream_url: "https://example.com/538.mp3",
      sort_order: 30,
    });
  });

  it("shows why the server turned a station down", async () => {
    globalThis.fetch = mockApi({ writeOk: false, detail: "stream_url must start with https://" });
    const given = await renderLoaded();

    await fireEvent.click(screen.getByText("Nieuwe zender"));
    await fireEvent.input(screen.getByLabelText("Naam"), { target: { value: "Bad" } });
    await fireEvent.click(screen.getByText("Opslaan"));

    await waitFor(() =>
      expect(given.onError).toHaveBeenCalledWith("stream_url must start with https://"),
    );
  });

  it("takes a station off the air", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getAllByText("Uit de lucht halen")[0]);

    await waitFor(() => expect(write("PUT")).toBeTruthy());
    expect(write("PUT")[0]).toBe("http://muma/api/radio/stations/slam");
    expect(JSON.parse(write("PUT")[1].body)).toEqual({ enabled: false });
  });

  it("asks before it removes a station", async () => {
    await renderLoaded();
    vi.spyOn(window, "confirm").mockReturnValue(false);

    await fireEvent.click(screen.getAllByLabelText("Verwijderen")[0]);
    expect(write("DELETE")).toBeUndefined();

    window.confirm.mockReturnValue(true);
    await fireEvent.click(screen.getAllByLabelText("Verwijderen")[0]);
    await waitFor(() => expect(write("DELETE")[0]).toBe("http://muma/api/radio/stations/slam"));
  });
});
