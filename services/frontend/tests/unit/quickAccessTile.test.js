/**
 * The compact tile Home and the preset grids share: a solid colour with an icon watermark,
 * or a cover photo when one is given instead. Styling itself (`BrowseGrid.svelte`'s look,
 * shrunk down) is not worth asserting on; what matters is that a cover replaces the coloured
 * icon rather than sitting alongside it, that a custom icon path actually reaches the SVG, and
 * that a tap still fires.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";

import QuickAccessTile from "../../src/lib/QuickAccessTile.svelte";

describe("QuickAccessTile", () => {
  it("shows a coloured icon tile without a cover", () => {
    const { container } = render(QuickAccessTile, {
      title: "Daily Mix",
      subtitle: "Angerfist – Raise Your Fist",
      color: "#8C67AB",
    });

    const button = screen.getByRole("button");
    expect(button.style.backgroundColor).toBe("rgb(140, 103, 171)");
    expect(screen.getByText("Daily Mix")).toBeTruthy();
    expect(screen.getByText("Angerfist – Raise Your Fist")).toBeTruthy();
    expect(container.querySelector("svg path")).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  it("renders the given icon path instead of the default note", () => {
    const shuffle = "M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41z";
    const { container } = render(QuickAccessTile, { title: "Random", icon: shuffle });

    expect(container.querySelector("svg path").getAttribute("d")).toBe(shuffle);
  });

  it("falls back to the note icon when none is given", () => {
    const { container } = render(QuickAccessTile, { title: "Recent" });

    expect(container.querySelector("svg path").getAttribute("d")).toBe(
      "M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z",
    );
  });

  it("renders a cover as a full-bleed background instead of the icon", () => {
    const { container } = render(QuickAccessTile, {
      title: "Memories",
      cover: "https://lms.example/getCoverArt?id=42",
    });

    const button = screen.getByRole("button");
    expect(button.getAttribute("style")).toContain(
      'background-image: url("https://lms.example/getCoverArt?id=42")',
    );
    expect(container.querySelector("svg")).toBeNull();
  });

  it("hands the click back", async () => {
    const onclick = vi.fn();
    render(QuickAccessTile, { title: "Starred", onclick });

    await fireEvent.click(screen.getByRole("button"));

    expect(onclick).toHaveBeenCalled();
  });
});
