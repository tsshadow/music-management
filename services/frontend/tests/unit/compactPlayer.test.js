import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import CompactPlayer from "../../src/lib/CompactPlayer.svelte";

const TRACK = { id: "song-1", title: "Raise Your Fist", artist: "Angerfist" };

function renderCompact(props = {}) {
  const handlers = {
    ontogglePlay: vi.fn(),
    onnext: vi.fn(),
    onprev: vi.fn(),
    onrate: vi.fn(),
  };
  render(CompactPlayer, { track: TRACK, progress: 60, duration: 240, ...handlers, ...props });
  return handlers;
}

describe("CompactPlayer", () => {
  it("shows the title, the artist and the progress of the track", () => {
    renderCompact();

    expect(screen.getByTestId("compact-title").textContent).toBe("Raise Your Fist");
    expect(screen.getByText("Angerfist")).toBeTruthy();
    expect(screen.getByTestId("compact-progress").firstElementChild.style.width).toBe("25%");
  });

  it("calls back into the player for play, previous and next", async () => {
    const handlers = renderCompact();

    await fireEvent.click(screen.getByLabelText("Afspelen"));
    await fireEvent.click(screen.getByLabelText("Vorige"));
    await fireEvent.click(screen.getByLabelText("Volgende"));

    expect(handlers.ontogglePlay).toHaveBeenCalledTimes(1);
    expect(handlers.onprev).toHaveBeenCalledTimes(1);
    expect(handlers.onnext).toHaveBeenCalledTimes(1);
  });

  it("labels the button pause while playing", () => {
    renderCompact({ playing: true });

    expect(screen.getByLabelText("Pauze")).toBeTruthy();
  });

  it("rates through the player's own function", async () => {
    const handlers = renderCompact({ rating: 2 });

    await fireEvent.click(screen.getByLabelText("4 sterren"));

    expect(handlers.onrate).toHaveBeenCalledWith(4);
    expect(screen.getByLabelText("2 sterren").className).toMatch(/text-brand/);
  });

  it("hides the stars when asked to", () => {
    renderCompact({ showRating: false });

    expect(screen.queryByTestId("compact-stars")).toBeNull();
  });

  it("shows a live station without skip, stars or progress", () => {
    renderCompact({ isLiveStation: true });

    expect(screen.queryByLabelText("Volgende")).toBeNull();
    expect(screen.queryByTestId("compact-stars")).toBeNull();
    expect(screen.queryByTestId("compact-progress")).toBeNull();
    expect(screen.getByLabelText("Afspelen")).toBeTruthy();
  });

  it("says nothing plays without a track, with play disabled", () => {
    renderCompact({ track: null });

    expect(screen.getByText("Niets aan het afspelen")).toBeTruthy();
    expect(screen.getByLabelText("Afspelen").disabled).toBe(true);
  });

  it("shows the queue restore in place of nothing playing", () => {
    renderCompact({ track: null, restoringQueue: true });

    expect(screen.getAllByText("Wachtrij wordt hersteld…").length).toBeGreaterThan(0);
  });

  it("disables skipping while the transport is locked", () => {
    renderCompact({ transportLocked: true });

    expect(screen.getByLabelText("Volgende").disabled).toBe(true);
    expect(screen.getByLabelText("Vorige").disabled).toBe(true);
  });
});
