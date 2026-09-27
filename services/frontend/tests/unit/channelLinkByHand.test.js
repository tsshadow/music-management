import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import ChannelLinkByHand from "../../src/lib/management/ChannelLinkByHand.svelte";

// docs/designs/channel-links/functional.md, "Linking by hand" (issue #58).

const HYSTA = {
  id: 7,
  platform: "soundcloud",
  name: "Hysta Official",
  track_count: 44,
  label: null,
  artist: null,
  open_proposals: 0,
};

function respond(body, ok = true, status = 200) {
  return { ok, status, json: async () => body };
}

describe("ChannelLinkByHand", () => {
  let calls;
  let onMessage;
  let onError;
  let onLinked;
  let linkResponse;

  beforeEach(() => {
    calls = [];
    onMessage = vi.fn();
    onError = vi.fn();
    onLinked = vi.fn();
    linkResponse = respond({
      status: "linked",
      channel_id: 7,
      kind: "artist",
      target_id: 20,
      target_name: "Hysta",
      queued: 44,
    });
    globalThis.fetch = vi.fn(async (url, init = {}) => {
      calls.push({ url, method: init.method || "GET", body: init.body });
      if (url.includes("/api/channel-links/channels?")) return respond([HYSTA]);
      if (url.includes("/api/channel-links/targets?kind=artist"))
        return respond([{ id: 20, name: "Hysta" }]);
      if (url.includes("/api/channel-links/targets?kind=label"))
        return respond([{ id: 10, name: "Hysta Records" }]);
      return linkResponse;
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function show(extra = {}) {
    return render(ChannelLinkByHand, {
      API_BASE: "/muma",
      getHeaders: (more = {}) => ({ ...more, "X-API-Key": "k" }),
      onMessage,
      onError,
      onLinked,
      ...extra,
    });
  }

  async function pick(inputLabel, typed, suggestion) {
    await fireEvent.input(screen.getByLabelText(inputLabel), { target: { value: typed } });
    const option = await screen.findByRole("button", { name: new RegExp(suggestion) });
    await fireEvent.click(option);
  }

  it("searches a channel and an approved artist and links them with PUT", async () => {
    show();
    await pick("Kanaal", "hysta", "Hysta Official");
    expect(calls[0].url).toBe("/muma/api/channel-links/channels?q=hysta&limit=20");
    expect(screen.getByTestId("channel-hand-link-channel-selected").textContent).toContain(
      "Hysta Official",
    );

    await fireEvent.click(screen.getByRole("radio", { name: "Artiest" }));
    await pick("Koppelen aan", "hys", "^Hysta$");
    expect(calls.at(-1).url).toBe("/muma/api/channel-links/targets?kind=artist&q=hys&limit=20");

    await fireEvent.click(screen.getByRole("button", { name: /^Koppelen$/ }));
    await waitFor(() => expect(onLinked).toHaveBeenCalled());
    const put = calls.at(-1);
    expect(put).toEqual({
      url: "/muma/api/channel-links/channels/7/artist",
      method: "PUT",
      body: JSON.stringify({ target_id: 20 }),
    });
    expect(onMessage).toHaveBeenCalledWith(
      "Hysta Official gekoppeld aan Hysta; 44 bestanden staan klaar voor de tagger.",
    );
  });

  it("shows the server's reason when it refuses the link", async () => {
    linkResponse = respond({ detail: "Only an approved artist can be linked" }, false, 409);
    show();
    await pick("Kanaal", "hysta", "Hysta Official");
    await pick("Koppelen aan", "hys", "Hysta Records");
    await fireEvent.click(screen.getByRole("button", { name: /^Koppelen$/ }));
    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith("Only an approved artist can be linked"),
    );
    expect(onLinked).not.toHaveBeenCalled();
  });

  it("starts from a channel handed over by the coverage table, on the kind it lacks", async () => {
    show({ initialChannel: { ...HYSTA, label: { id: 10, name: "Hysta Records" } } });
    expect(screen.getByTestId("channel-hand-link-channel-selected").textContent).toContain(
      "Hysta Official",
    );
    expect(screen.getByRole("radio", { name: "Artiest" }).getAttribute("aria-checked")).toBe(
      "true",
    );
    // The label is taken: switching to it says so and offers nothing to submit.
    await fireEvent.click(screen.getByRole("radio", { name: "Label" }));
    expect(screen.getByText(/Al gekoppeld aan Hysta Records/)).toBeTruthy();
    expect(screen.getByRole("button", { name: /^Koppelen$/ }).disabled).toBe(true);
  });

  it("cannot submit until a channel and a target are picked", async () => {
    show();
    expect(screen.getByRole("button", { name: /^Koppelen$/ }).disabled).toBe(true);
    await pick("Kanaal", "hysta", "Hysta Official");
    expect(screen.getByRole("button", { name: /^Koppelen$/ }).disabled).toBe(true);
  });
});
