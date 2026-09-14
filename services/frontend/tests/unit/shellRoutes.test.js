import { describe, it, expect } from "vitest";
import { deepLinkAction, randomTracksUrl } from "../../src/lib/shellRoutes.js";

/**
 * The routes the shell sends in are a cross-process contract: they come out of
 * `PendingIntent`s the system is already holding, from installs that predate
 * this code. A route that stops being understood is a tile that does nothing.
 */

describe("deepLinkAction", () => {
  it("opens the queue for a tap on the notification", () => {
    expect(deepLinkAction("player")).toEqual({ kind: "queue" });
  });

  it("opens the queue on desktop even when asked explicitly", () => {
    expect(deepLinkAction("player", { isMobile: false })).toEqual({ kind: "queue" });
  });

  // The phone has no desktop queue panel: the same notification tap opens the
  // full-screen Now Playing view instead, which is where the transport lives
  // on that layout.
  it("opens Now Playing for the same tap on the phone", () => {
    expect(deepLinkAction("player", { isMobile: true })).toEqual({ kind: "now-playing" });
  });

  it("plays something for the car-mode 'play random' intent", () => {
    expect(deepLinkAction("random")).toEqual({ kind: "random" });
  });

  it("routes a search intent to the search view with its query", () => {
    expect(deepLinkAction("search:hardstyle")).toEqual({
      kind: "view",
      view: "search:hardstyle",
    });
  });

  // The query is free text from a voice intent: colons, slashes and spaces all
  // occur, and the route takes everything after the first colon whole.
  it("keeps a query that contains a colon", () => {
    expect(deepLinkAction("search:defqon.1: blue stage").view).toBe("search:defqon.1: blue stage");
  });

  it("sends an empty search home rather than to an empty result", () => {
    expect(deepLinkAction("search:   ")).toEqual({ kind: "view", view: "home" });
  });

  // The voice screen is a Svelte screen now: the quick-settings tile, the
  // launcher shortcut and a car-mode microphone all arrive as this route (see
  // `VoiceTileService.EXTRA_OPEN_VOICE` and `CapacitorActivity.ROUTE_VOICE`),
  // and it must open the real screen rather than the `unbuilt` placeholder.
  it("opens the voice screen for the voice route", () => {
    expect(deepLinkAction("voice")).toEqual({ kind: "view", view: "voice" });
  });

  // The car-mode notification and its "open car mode from the overflow menu"
  // twin both land here now that the Svelte screen exists too.
  it("opens the car screen for the car-mode notification", () => {
    expect(deepLinkAction("car")).toEqual({ kind: "view", view: "car" });
  });

  it.each([undefined, null, "", "something-else"])("sends %s home", (route) => {
    expect(deepLinkAction(route)).toEqual({ kind: "view", view: "home" });
  });
});

describe("randomTracksUrl", () => {
  // Ten minutes is the boundary the track list uses. A "play something" from a
  // car at the moment somebody asked for a set must not answer with pop songs.
  it("asks for sets in sets mode and for tracks otherwise", () => {
    expect(randomTracksUrl({ mode: "sets", auth: "u=user", seed: 7 })).toContain("minDuration=10");
    expect(randomTracksUrl({ mode: "songs", auth: "u=user", seed: 7 })).toContain("maxDuration=10");
  });

  it("is one page of random tracks, signed", () => {
    const url = randomTracksUrl({ mode: "songs", auth: "u=user&p=x", seed: 7, count: 25 });

    expect(url).toBe(
      "/rest/getSpotifyTracks?sort=random&seed=7&offset=0&count=25&maxDuration=10&u=user&p=x",
    );
  });
});
