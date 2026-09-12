import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/svelte";
import { get } from "svelte/store";
import ModeChips from "../../src/lib/ModeChips.svelte";
import { viewMode } from "../../src/lib/store.js";

/** The group ModeChips renders its two pills in. */
function group() {
  return within(screen.getByRole("group", { name: "Modus wisselen" }));
}

describe("ModeChips", () => {
  beforeEach(() => {
    viewMode.set("songs");
  });

  it("marks the current mode's pill as pressed", () => {
    render(ModeChips);

    expect(group().getByRole("button", { name: "Nummers" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(group().getByRole("button", { name: "Sets" })).toHaveAttribute("aria-pressed", "false");
  });

  it("switches to sets without navigating anywhere", () => {
    render(ModeChips);

    fireEvent.click(group().getByRole("button", { name: "Sets" }));

    expect(get(viewMode)).toBe("sets");
  });

  it("switches back to songs", () => {
    viewMode.set("sets");
    render(ModeChips);

    fireEvent.click(group().getByRole("button", { name: "Nummers" }));

    expect(get(viewMode)).toBe("songs");
  });

  it("moves the pressed pill along with an external mode change", async () => {
    render(ModeChips);

    viewMode.set("sets");

    expect(await group().findByRole("button", { name: "Sets" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
