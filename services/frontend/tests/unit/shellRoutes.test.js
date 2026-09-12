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

  // Phase 4 builds these screens. Until then the tap has to land somewhere
  // usable and the action log has to say what was asked for, because that is
  // the only way "it did nothing" reads back out of a crash report.
  it.each(["car", "voice"])("lands %s on home and records that it is unbuilt", (route) => {
    expect(deepLinkAction(route)).toEqual({ kind: "view", view: "home", unbuilt: route });
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
