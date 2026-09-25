import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import ChannelLinkProposals from "../../src/lib/management/ChannelLinkProposals.svelte";

function proposals() {
  return [
    {
      id: 5,
      channel_id: 1,
      platform: "soundcloud",
      channel_name: "TRAXTORM",
      kind: "label",
      target_id: 10,
      target_name: "Traxtorm Records",
      source: "name",
      status: "new",
      track_count: 1200,
    },
    {
      id: 6,
      channel_id: 2,
      platform: "youtube",
      channel_name: "D-Sturb",
      kind: "artist",
      target_id: 20,
      target_name: "D-Sturb Official",
      source: "alias",
      status: "new",
      track_count: 40,
    },
  ];
}

describe("ChannelLinkProposals", () => {
  let calls;
  let onMessage;
  let onError;

  beforeEach(() => {
    calls = [];
    onMessage = vi.fn();
    onError = vi.fn();
    globalThis.fetch = vi.fn(async (url, init = {}) => {
      calls.push({ url, method: init.method || "GET" });
      if (url.endsWith("/refresh")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            created: 2,
            open: 2,
            withdrawn: 0,
            ambiguous: 1,
          }),
        };
      }
      if (url.endsWith("/confirm")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ status: "confirmed" }),
        };
      }
      if (url.endsWith("/reject")) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ status: "rejected" }),
        };
      }
      return { ok: true, status: 200, json: async () => proposals() };
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  function show() {
    return render(ChannelLinkProposals, {
      API_BASE: "/muma",
      getHeaders: () => ({ "X-API-Key": "k" }),
      onMessage,
      onError,
    });
  }

  it("lists the open proposals with kind, reason and track count", async () => {
    show();
    await waitFor(() => expect(screen.getByText("TRAXTORM")).toBeTruthy());
    expect(calls[0].url).toBe("/muma/api/channel-links/proposals?status=new");
    expect(screen.getByText("Traxtorm Records")).toBeTruthy();
    expect(screen.getByText("Zelfde naam")).toBeTruthy();
    expect(screen.getByText("Alias")).toBeTruthy();
    expect(screen.getByText("1.200")).toBeTruthy();
  });

  it("filters on kind", async () => {
    show();
    await waitFor(() => expect(screen.getByText("TRAXTORM")).toBeTruthy());
    await fireEvent.change(screen.getByLabelText("Soort"), {
      target: { value: "artist" },
    });
    await waitFor(() => expect(screen.queryByText("TRAXTORM")).toBeNull());
    expect(screen.getByText("D-Sturb")).toBeTruthy();
  });

  it("confirms through the confirm endpoint and drops the row", async () => {
    show();
    await waitFor(() => expect(screen.getByText("TRAXTORM")).toBeTruthy());
    await fireEvent.click(screen.getAllByRole("button", { name: /Bevestigen/ })[0]);
    await waitFor(() => expect(screen.queryByText("TRAXTORM")).toBeNull());
    expect(calls.at(-1)).toEqual({
      url: "/muma/api/channel-links/proposals/5/confirm",
      method: "POST",
    });
    expect(onMessage).toHaveBeenCalledWith("TRAXTORM gekoppeld aan Traxtorm Records");
  });

  it("rejects through the reject endpoint", async () => {
    show();
    await waitFor(() => expect(screen.getByText("D-Sturb")).toBeTruthy());
    await fireEvent.click(screen.getAllByRole("button", { name: /Afwijzen/ })[1]);
    await waitFor(() => expect(screen.queryByText("D-Sturb")).toBeNull());
    expect(calls.at(-1)).toEqual({
      url: "/muma/api/channel-links/proposals/6/reject",
      method: "POST",
    });
  });

  it("runs the search and reports its counts", async () => {
    show();
    await waitFor(() => expect(screen.getByText("TRAXTORM")).toBeTruthy());
    await fireEvent.click(screen.getByRole("button", { name: /Voorstellen zoeken/ }));
    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith(
        "2 nieuwe voorstellen, 2 open, 0 vervallen, 1 kanalen overgeslagen als dubbelzinnig.",
      ),
    );
    expect(
      calls.some(
        (c) => c.url === "/muma/api/channel-links/proposals/refresh" && c.method === "POST",
      ),
    ).toBe(true);
  });

  it("says so when there is nothing open", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => [],
    }));
    show();
    await waitFor(() => expect(screen.getByText(/Geen open voorstellen/)).toBeTruthy());
  });

  it("names the reason when the list cannot be loaded", async () => {
    globalThis.fetch = vi.fn(async () => ({
      ok: false,
      status: 500,
      json: async () => ({ detail: "No database connection" }),
    }));
    show();
    await waitFor(() => expect(screen.getByText("No database connection")).toBeTruthy());
  });
});
