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

  // The Codex design review: both words stay visible in one compact segmented
  // control (no icons, no abbreviations, no active-word-only pill), the active
  // segment in the brand colour and the inactive one dimmed rather than boxed.
  it("renders as a single compact segmented control, not two loose pills", () => {
    render(ModeChips);

    const songs = group().getByRole("button", { name: "Nummers" });
    const sets = group().getByRole("button", { name: "Sets" });
    expect(songs.parentElement).toBe(sets.parentElement);
    expect(songs.parentElement.className).toContain("rounded-full");
    expect(songs.parentElement.className).toContain("border");
  });

  it("colours the active songs segment green and dims the inactive sets segment", () => {
    render(ModeChips);

    expect(group().getByRole("button", { name: "Nummers" }).className).toContain("bg-brand-green");
    expect(group().getByRole("button", { name: "Sets" }).className).toContain("text-white/60");
  });

  it("colours the active sets segment blue once switched", () => {
    viewMode.set("sets");
    render(ModeChips);

    expect(group().getByRole("button", { name: "Sets" }).className).toContain("bg-brand-blue");
    expect(group().getByRole("button", { name: "Nummers" }).className).toContain("text-white/60");
  });
});
