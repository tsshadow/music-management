/**
 * One memories year tile: a cover collage, or -- when the year has no cover art at all -- a
 * tinted panel with the year, matching the player's own no-artwork fallback (`Artwork.svelte`)
 * instead of the generic Spotify placeholder image. Shared between the Memories grid and
 * PhoneHome's home-screen year row.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/svelte";
import MemoryYearCard from "../../src/lib/MemoryYearCard.svelte";

const tile = {
  year: 2016,
  yearsAgo: 8,
  exact: true,
  count: 2,
  top: [{ id: "s1", title: "Track A" }],
  covers: [],
};

describe("MemoryYearCard", () => {
  it("shows the tinted Artwork panel with the year when the tile has no covers", () => {
    render(MemoryYearCard, { tile, onopen: vi.fn(), onplay: vi.fn() });

    const panel = screen.getByTestId("artwork-panel");
    expect(within(panel).getByText("2016")).toBeTruthy();
    expect(document.querySelector('[src="/images/spotify-fallback.svg"]')).toBeNull();
  });

  it("shows the cover collage instead of the panel when the tile has covers", () => {
    const { container } = render(MemoryYearCard, {
      tile: { ...tile, covers: ["cov-1"] },
      onopen: vi.fn(),
      onplay: vi.fn(),
    });

    expect(screen.queryByTestId("artwork-panel")).toBeNull();
    // The collage's covers are decorative (`alt=""`), so they carry no accessible "img" role;
    // a plain element query is the only reliable way to count them.
    expect(container.querySelectorAll("img")).toHaveLength(1);
  });

  it("opens the year when the card is tapped", async () => {
    const onopen = vi.fn();
    render(MemoryYearCard, { tile, onopen, onplay: vi.fn() });

    await fireEvent.click(screen.getByRole("button", { name: "2016 openen" }));

    expect(onopen).toHaveBeenCalledWith(2016);
  });
});
