import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/svelte";

import About from "../../src/lib/settings/About.svelte";

function respond(handlers) {
  return vi.fn(async (url) => {
    for (const [fragment, response] of Object.entries(handlers)) {
      if (String(url).includes(fragment)) return response();
    }
    return { ok: false, json: async () => ({}) };
  });
}

const PING_OK = () => ({
  ok: true,
  json: async () => ({ "subsonic-response": { status: "ok", serverVersion: "0.0.60" } }),
});

const NO_RELEASE_NOTES = () => ({ ok: false, json: async () => [] });

describe("About", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  beforeEach(() => {
    globalThis.fetch = respond({ "/rest/ping": PING_OK, "release-notes.json": NO_RELEASE_NOTES });
  });

  it("shows the server version it got from the ping", async () => {
    render(About);
    await waitFor(() => expect(screen.getByText("Versie 0.0.60")).toBeInTheDocument());
  });

  it("falls back to the plain version field when the server sends no serverVersion", async () => {
    globalThis.fetch = respond({
      "/rest/ping": () => ({
        ok: true,
        json: async () => ({ "subsonic-response": { status: "ok", version: "1.16.1" } }),
      }),
      "release-notes.json": NO_RELEASE_NOTES,
    });
    render(About);
    await waitFor(() => expect(screen.getByText("Versie 1.16.1")).toBeInTheDocument());
  });

  it("says the version is unknown rather than staying on the loading text", async () => {
    globalThis.fetch = respond({
      "/rest/ping": () => ({ ok: true, json: async () => ({}) }),
      "release-notes.json": NO_RELEASE_NOTES,
    });
    render(About);
    await waitFor(() => expect(screen.getByText("Versie onbekend")).toBeInTheDocument());
  });

  it("survives a ping that fails outright", async () => {
    globalThis.fetch = respond({
      "/rest/ping": () => {
        throw new Error("offline");
      },
      "release-notes.json": NO_RELEASE_NOTES,
    });
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(About);
    await waitFor(() => expect(screen.getByText("Versie onbekend")).toBeInTheDocument());
  });

  it("tells the user when there are no release notes", async () => {
    render(About);
    await waitFor(() => expect(screen.getByText("Versie 0.0.60")).toBeInTheDocument());
    expect(screen.queryByText("0.0.59")).not.toBeInTheDocument();
  });

  it("renders the release notes grouped by category", async () => {
    globalThis.fetch = respond({
      "/rest/ping": PING_OK,
      "release-notes.json": () => ({
        ok: true,
        json: async () => [
          {
            version: "0.0.60",
            date: "2026-08-02",
            notes: { Toegevoegd: ["Radio mode"], Opgelost: ["Artist images"] },
          },
        ],
      }),
    });
    render(About);
    await waitFor(() => expect(screen.getByText("Radio mode")).toBeInTheDocument());
    expect(screen.getByText("Artist images")).toBeInTheDocument();
    expect(screen.getByText("2026-08-02")).toBeInTheDocument();
  });

  it("explains how car mode turns on, since Android Auto is mentioned nowhere else on the web", async () => {
    render(About);
    await waitFor(() => expect(screen.getByText("Versie 0.0.60")).toBeInTheDocument());

    expect(screen.getByText("Hoe de automodus aangaat")).toBeInTheDocument();
    expect(screen.getByText(/Android Auto/)).toBeInTheDocument();
  });

  it("survives release notes that cannot be fetched", async () => {
    globalThis.fetch = respond({
      "/rest/ping": PING_OK,
      "release-notes.json": () => {
        throw new Error("offline");
      },
    });
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(About);
    await waitFor(() => expect(screen.getByText("Versie 0.0.60")).toBeInTheDocument());
  });
});
