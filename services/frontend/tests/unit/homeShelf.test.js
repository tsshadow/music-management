import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import HomeShelf from "../../src/lib/HomeShelf.svelte";
import { isMobile } from "../../src/lib/store.js";

const TRACKS = [
  { id: "song-1", title: "Raise Your Fist", artist: "Angerfist" },
  { id: "song-2", title: "The Fear", artist: "Angerfist" },
  { id: "song-3", title: "Incoming Doom", artist: "Angerfist" },
];

afterEach(() => {
  isMobile.set(false);
});

describe("HomeShelf", () => {
  it("renders a card per track under the heading", () => {
    render(HomeShelf, { title: "Nummers", tracks: TRACKS, showAllLabel: "Alles tonen" });

    expect(screen.getByText("Nummers")).toBeTruthy();
    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
    expect(screen.getByText("The Fear")).toBeTruthy();
    expect(screen.getByText("Incoming Doom")).toBeTruthy();
  });

  it("calls onshowall when the label is clicked", async () => {
    const onshowall = vi.fn();
    render(HomeShelf, { title: "Nummers", tracks: TRACKS, showAllLabel: "Alles tonen", onshowall });

    await fireEvent.click(screen.getByText("Alles tonen"));

    expect(onshowall).toHaveBeenCalled();
  });

  it("shows the empty message when there are no tracks", () => {
    render(HomeShelf, { title: "Nummers", tracks: [], noTracksText: "Nog niets hier" });

    expect(screen.getByText("Nog niets hier")).toBeTruthy();
  });

  // The card grid on a phone put one row per section on screen and forced endless scrolling.
  // Below `isMobile` the row becomes a single horizontally-scrolling shelf instead, with each
  // card pinned to a fixed width so the row actually scrolls rather than wrapping.
  it("lays the row out as a fixed-width horizontal shelf on a phone", () => {
    isMobile.set(true);
    render(HomeShelf, { title: "Nummers", tracks: TRACKS, showAllLabel: "Alles tonen" });

    const card = screen.getByText("Raise Your Fist").closest('[role="button"]');
    const wrapper = card.parentElement;
    const row = wrapper.parentElement;
    expect(row.className).toContain("overflow-x-auto");
    expect(wrapper.className).toContain("w-[140px]");
  });

  // Desktop keeps the grid it always had -- the point of `isMobile` driving this instead of a
  // bare `md:` class is that a test can pin the desktop branch down explicitly.
  it("keeps the desktop grid layout when not on a phone", () => {
    isMobile.set(false);
    render(HomeShelf, { title: "Nummers", tracks: TRACKS, showAllLabel: "Alles tonen" });

    const card = screen.getByText("Raise Your Fist").closest('[role="button"]');
    const row = card.parentElement.parentElement;
    expect(row.className).toContain("grid");
    expect(row.className).not.toContain("overflow-x-auto");
  });
});
