import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/svelte";

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

/** The shell, as the About page sees it: an APK with a version, notes and an update answer. */
function nativePlatform({ update = null, notes = "" } = {}) {
  return {
    system: {
      isNative: true,
      serverUrl: () => ({ subsonic: "https://lms.example", mumaApi: "https://lms.example/muma" }),
      appInfo: vi.fn(async () => ({
        version: "6.36.0",
        versionCode: 313,
        buildType: "debug",
        packageName: "org.example.mumamobile.debug",
        androidVersion: "15 (API 35)",
        device: "Google Pixel 8",
      })),
      releaseNotes: vi.fn(async () => notes),
      checkForUpdate: vi.fn(async () => {
        if (update instanceof Error) throw update;
        return update;
      }),
      openUrl: vi.fn(async () => {}),
    },
  };
}

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
    vi.spyOn(console, "warn").mockImplementation(() => {});
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
    vi.spyOn(console, "warn").mockImplementation(() => {});
    render(About);
    await waitFor(() => expect(screen.getByText("Versie 0.0.60")).toBeInTheDocument());
  });

  it("lists the MuMa API version from /health next to the LMS version", async () => {
    globalThis.fetch = respond({
      "/rest/ping": PING_OK,
      "/health": () => ({
        ok: true,
        status: 200,
        json: async () => ({ version: "0.61.0", status: "ok" }),
      }),
      "release-notes.json": NO_RELEASE_NOTES,
    });
    render(About);
    await waitFor(() => expect(screen.getByText("Versie 0.61.0")).toBeInTheDocument());
    expect(screen.getByText("0.0.60")).toBeInTheDocument();
  });

  it("lists the bundle's git hash and build time when version.json is there", async () => {
    globalThis.fetch = respond({
      "/rest/ping": PING_OK,
      "version.json": () => ({
        ok: true,
        json: async () => ({ version: "7ef1b495a", builtAt: "2026-09-15T10:00:00.000Z" }),
      }),
      "release-notes.json": NO_RELEASE_NOTES,
    });
    render(About);
    await waitFor(() => expect(screen.getByText("7ef1b495a")).toBeInTheDocument());
  });

  it("has no App block and no update button in a browser tab", async () => {
    render(About);
    await waitFor(() => expect(screen.getByText("Versie 0.0.60")).toBeInTheDocument());
    expect(screen.queryByTestId("about-app")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Controleren op updates" }),
    ).not.toBeInTheDocument();
  });

  it("describes the APK and shows the app's own changelog inside the shell", async () => {
    const platform = nativePlatform({
      notes: "## [6.36.0] - 2026-09-14\n\n### Fixed\n\n- Het rijscherm loopt weer mee.\n",
    });
    render(About, { props: { platform } });

    await waitFor(() => expect(screen.getByText("Versie 6.36.0 (313)")).toBeInTheDocument());
    expect(screen.getByTestId("about-app")).toHaveTextContent("debug");
    expect(screen.getByTestId("about-app")).toHaveTextContent("org.example.mumamobile.debug");
    expect(screen.getByTestId("about-app")).toHaveTextContent("15 (API 35)");
    expect(screen.getByTestId("about-app")).toHaveTextContent("Google Pixel 8");
    expect(screen.getByText("Het rijscherm loopt weer mee.")).toBeInTheDocument();
    expect(screen.getByTestId("about-server")).toHaveTextContent("https://lms.example");
  });

  it("checks for an update on request and says when there is a newer build", async () => {
    const platform = nativePlatform({
      update: {
        available: true,
        currentVersionCode: 313,
        currentVersionName: "6.36.0",
        latestVersionCode: 314,
        latestVersionName: "6.36.1",
        url: "https://apk.example/dl/314?u=guest&p=guest",
      },
    });
    render(About, { props: { platform } });
    await waitFor(() => expect(screen.getByText("Versie 6.36.0 (313)")).toBeInTheDocument());

    await fireEvent.click(screen.getByRole("button", { name: "Controleren op updates" }));

    await waitFor(() =>
      expect(screen.getByTestId("update-outcome")).toHaveTextContent(
        "Nieuwere versie beschikbaar: 6.36.1",
      ),
    );
    expect(platform.system.checkForUpdate).toHaveBeenCalledTimes(1);
  });

  it("says so when the build is the newest, and reports a failed check as failed", async () => {
    const upToDate = nativePlatform({
      update: {
        available: false,
        currentVersionCode: 313,
        currentVersionName: "6.36.0",
        latestVersionCode: 313,
        latestVersionName: "6.36.0",
        url: "",
      },
    });
    const { unmount } = render(About, { props: { platform: upToDate } });
    await waitFor(() => expect(screen.getByText("Versie 6.36.0 (313)")).toBeInTheDocument());
    await fireEvent.click(screen.getByRole("button", { name: "Controleren op updates" }));
    await waitFor(() =>
      expect(screen.getByTestId("update-outcome")).toHaveTextContent("Je hebt de nieuwste versie."),
    );
    unmount();

    const failing = nativePlatform({
      update: new Error("update check failed: apk-hoster answered 503"),
    });
    render(About, { props: { platform: failing } });
    await waitFor(() => expect(screen.getByText("Versie 6.36.0 (313)")).toBeInTheDocument());
    await fireEvent.click(screen.getByRole("button", { name: "Controleren op updates" }));
    await waitFor(() =>
      expect(screen.getByTestId("update-outcome")).toHaveTextContent("Controleren is niet gelukt."),
    );
  });
});
