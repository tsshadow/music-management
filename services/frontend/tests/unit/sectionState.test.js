import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { createRawSnippet } from "svelte";
import SectionState from "../../src/lib/loading/SectionState.svelte";
import SkeletonRows from "../../src/lib/loading/SkeletonRows.svelte";
import Throbber from "../../src/lib/loading/Throbber.svelte";

/** A snippet rendering one element with the given test id. */
function snippet(testid) {
  return createRawSnippet(() => ({ render: () => `<div data-testid="${testid}"></div>` }));
}

/** One section of a page loading on its own (styleguide, Loading States). */
describe("SectionState", () => {
  it("shows the skeleton while the first answer is on its way", () => {
    render(SectionState, {
      status: "loading",
      skeleton: snippet("the-skeleton"),
      children: snippet("the-content"),
    });

    expect(screen.getByTestId("the-skeleton")).toBeTruthy();
    expect(screen.queryByTestId("the-content")).toBeNull();
  });

  it("shows its content once ready", () => {
    render(SectionState, {
      status: "ready",
      skeleton: snippet("the-skeleton"),
      children: snippet("the-content"),
    });

    expect(screen.getByTestId("the-content")).toBeTruthy();
    expect(screen.queryByTestId("the-skeleton")).toBeNull();
  });

  it("shows one error line with a retry that asks again", async () => {
    const onretry = vi.fn();
    render(SectionState, { status: "error", onretry, children: snippet("the-content") });

    expect(screen.getByRole("alert").textContent).toContain("Kon dit deel niet laden");
    expect(screen.queryByTestId("the-content")).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "Opnieuw" }));
    expect(onretry).toHaveBeenCalledTimes(1);
  });

  it("offers no button when there is nothing to retry with", () => {
    render(SectionState, { status: "error" });

    expect(screen.queryByRole("button")).toBeNull();
  });
});

describe("loading placeholders", () => {
  it("skeleton rows announce loading once and draw the requested number of rows", () => {
    render(SkeletonRows, { count: 3 });

    const status = screen.getByRole("status");
    expect(status.getAttribute("aria-label")).toBe("Laden...");
    expect(status.children).toHaveLength(3);
  });

  it("the throbber is a labelled status", () => {
    render(Throbber, { label: "Wacht op nummers" });

    expect(screen.getByRole("status", { name: "Wacht op nummers" })).toBeTruthy();
  });
});
