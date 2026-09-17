import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/svelte";
import MetaChips from "../../src/lib/MetaChips.svelte";

describe("MetaChips", () => {
  it("renders a navigable item as a button and calls back with its view", async () => {
    const onnavigate = vi.fn();
    render(MetaChips, { items: [{ text: "Hardstyle", view: "genre:Hardstyle" }], onnavigate });

    const chip = screen.getByText("Hardstyle");
    expect(chip.tagName).toBe("BUTTON");

    await chip.click();

    expect(onnavigate).toHaveBeenCalledWith("genre:Hardstyle");
  });

  it("renders an item with no view as a plain span, not a button", () => {
    const onnavigate = vi.fn();
    render(MetaChips, { items: [{ text: "Euphoric", view: null }], onnavigate });

    const chip = screen.getByText("Euphoric");
    expect(chip.tagName).toBe("SPAN");
  });

  it("renders one chip per item, in order", () => {
    render(MetaChips, {
      items: [
        { text: "Hardstyle", view: "genre:Hardstyle" },
        { text: "Hardcore", view: "genre:Hardcore" },
      ],
    });

    expect(screen.getByText("Hardstyle")).toBeTruthy();
    expect(screen.getByText("Hardcore")).toBeTruthy();
  });

  it("puts the given data-testid on each chip and the wrapping row", () => {
    render(MetaChips, {
      items: [{ text: "Hardstyle", view: "genre:Hardstyle", testid: "genre-chip" }],
      testid: "the-row",
    });

    expect(screen.getByTestId("the-row")).toBeTruthy();
    expect(screen.getByTestId("genre-chip")).toBeTruthy();
  });

  it("renders nothing but an empty row without items", () => {
    render(MetaChips, { items: [], testid: "empty-row" });

    expect(screen.getByTestId("empty-row").children.length).toBe(0);
  });
});
