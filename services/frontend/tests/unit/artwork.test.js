import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import Artwork from "../../src/lib/Artwork.svelte";

/**
 * The one artwork slot every player surface shares: cover -> artist image -> tinted title
 * panel, advanced by a real `onerror` rather than a mocked one, so these tests exercise the
 * same event `Player.svelte` and `NowPlaying.svelte` wire up.
 */
describe("Artwork", () => {
  it("shows the cover when there is one", () => {
    render(Artwork, {
      coverUrl: "https://example.test/cover.jpg",
      artistUrl: "https://example.test/artist.jpg",
      title: "Raise Your Fist",
    });

    const img = screen.getByAltText("Raise Your Fist");
    expect(img).toHaveAttribute("src", "https://example.test/cover.jpg");
  });

  it("falls through to the artist image once the cover fails to load", async () => {
    render(Artwork, {
      coverUrl: "https://example.test/cover.jpg",
      artistUrl: "https://example.test/artist.jpg",
      title: "Raise Your Fist",
    });

    await fireEvent.error(screen.getByAltText("Raise Your Fist"));

    expect(screen.getByAltText("Raise Your Fist")).toHaveAttribute(
      "src",
      "https://example.test/artist.jpg",
    );
  });

  it("falls through to the tinted panel once the artist image fails too", async () => {
    render(Artwork, {
      coverUrl: "https://example.test/cover.jpg",
      artistUrl: "https://example.test/artist.jpg",
      title: "Raise Your Fist",
    });

    await fireEvent.error(screen.getByAltText("Raise Your Fist"));
    await fireEvent.error(screen.getByAltText("Raise Your Fist"));

    expect(screen.queryByAltText("Raise Your Fist")).toBeNull();
    expect(screen.getByTestId("artwork-panel")).toBeTruthy();
    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
  });

  it("starts straight at the artist image without a cover", () => {
    render(Artwork, {
      coverUrl: null,
      artistUrl: "https://example.test/artist.jpg",
      title: "Raise Your Fist",
    });

    expect(screen.getByAltText("Raise Your Fist")).toHaveAttribute(
      "src",
      "https://example.test/artist.jpg",
    );
  });

  it("starts straight at the panel without a cover or an artist image", () => {
    render(Artwork, { coverUrl: null, artistUrl: null, title: "Raise Your Fist" });

    expect(screen.getByTestId("artwork-panel")).toBeTruthy();
    expect(screen.getByText("Raise Your Fist")).toBeTruthy();
  });

  it("never renders the spotify-fallback mark", async () => {
    render(Artwork, {
      coverUrl: "https://example.test/cover.jpg",
      artistUrl: "https://example.test/artist.jpg",
      title: "Raise Your Fist",
    });

    await fireEvent.error(screen.getByAltText("Raise Your Fist"));
    await fireEvent.error(screen.getByAltText("Raise Your Fist"));

    expect(document.querySelector('[src="/images/spotify-fallback.svg"]')).toBeNull();
  });

  it("resets to the cover when a new track's coverUrl arrives, even after a stale error", async () => {
    const { rerender } = render(Artwork, {
      coverUrl: "https://example.test/cover-1.jpg",
      artistUrl: null,
      title: "Raise Your Fist",
    });

    // Track 1 has no artist image either, so its failed cover lands on the panel.
    await fireEvent.error(screen.getByAltText("Raise Your Fist"));
    expect(screen.getByTestId("artwork-panel")).toBeTruthy();

    // Track 2 has a cover of its own; the stale error must not skip it.
    await rerender({
      coverUrl: "https://example.test/cover-2.jpg",
      artistUrl: null,
      title: "Encore",
    });

    expect(screen.getByAltText("Encore")).toHaveAttribute(
      "src",
      "https://example.test/cover-2.jpg",
    );
  });

  it("colours the panel with the given tint", () => {
    render(Artwork, { coverUrl: null, artistUrl: null, tint: "#ff4d00", title: "Raise Your Fist" });

    expect(screen.getByTestId("artwork-panel")).toHaveStyle({ backgroundColor: "#ff4d00" });
  });

  it("falls back to the neutral panel colour without a tint", () => {
    render(Artwork, { coverUrl: null, artistUrl: null, tint: null, title: "Raise Your Fist" });

    expect(screen.getByTestId("artwork-panel")).toHaveStyle({ backgroundColor: "#282828" });
  });
});
