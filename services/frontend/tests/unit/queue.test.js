import { describe, it, expect, beforeEach } from "vitest";
import { get } from "svelte/store";
import { activeView, playlist, queueSource } from "../../src/lib/store.js";
import { startQueue, viewLabel } from "../../src/lib/queue.js";

const TRACKS = [{ id: "song-1" }, { id: "song-2" }];

describe("startQueue", () => {
  beforeEach(() => {
    activeView.set("home");
    playlist.set([]);
    queueSource.set(null);
  });

  it("sets both the playlist and the queue source", () => {
    activeView.set("genre:Hardcore");

    startQueue(TRACKS, { name: "Hardcore" });

    expect(get(playlist)).toEqual(TRACKS);
    expect(get(queueSource)).toEqual({ view: "genre:Hardcore", name: "Hardcore" });
  });

  it("defaults the view to whatever is currently active when none is given", () => {
    activeView.set("starred");

    startQueue(TRACKS);

    expect(get(queueSource)).toEqual({ view: "starred", name: null });
  });

  it("clears the queue source when the view is explicitly null, for a restore", () => {
    queueSource.set({ view: "genre:Hardcore", name: "Hardcore" });

    startQueue(TRACKS, { view: null });

    expect(get(queueSource)).toBeNull();
    expect(get(playlist)).toEqual(TRACKS);
  });

  it("clears the queue source when the queue is emptied the same way", () => {
    queueSource.set({ view: "genre:Hardcore", name: "Hardcore" });

    startQueue([], { view: null });

    expect(get(queueSource)).toBeNull();
    expect(get(playlist)).toEqual([]);
  });
});

describe("viewLabel", () => {
  it("names a whole view via its existing nav key", () => {
    expect(viewLabel("starred")).toBe("Favorieten");
    expect(viewLabel("songs")).toBe("Nummers");
    expect(viewLabel("home")).toBe("Home");
    expect(viewLabel("memories")).toBe("Memories");
  });

  it("returns the typed query for a search view, untranslated", () => {
    expect(viewLabel("search:hardcore anthems")).toBe("hardcore anthems");
  });

  it("is null for a view with no whole-view label, and for nothing at all", () => {
    expect(viewLabel("artist:123")).toBeNull();
    expect(viewLabel(null)).toBeNull();
    expect(viewLabel(undefined)).toBeNull();
  });
});
