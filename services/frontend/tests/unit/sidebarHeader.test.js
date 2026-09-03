import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { get } from "svelte/store";
import SidebarHeader from "../../src/lib/SidebarHeader.svelte";
import { activeView, pushedHistoryEntries } from "../../src/lib/store.js";

describe("SidebarHeader", () => {
  beforeEach(() => {
    activeView.set("home");
    pushedHistoryEntries.set(0);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("offers no way back from the player, which is where back would lead", () => {
    render(SidebarHeader);

    expect(screen.queryByText("Terug")).toBeNull();
  });

  it.each(["management", "settings"])("offers a way back from %s", (view) => {
    activeView.set(view);

    render(SidebarHeader);

    expect(screen.getByText("Terug")).toBeTruthy();
  });

  it("walks the browser history back when this session put something there", async () => {
    const back = vi.spyOn(window.history, "back").mockImplementation(() => {});
    activeView.set("management");
    pushedHistoryEntries.set(2);
    render(SidebarHeader);

    await fireEvent.click(screen.getByText("Terug"));

    expect(back).toHaveBeenCalled();
  });

  // Arriving straight on /management/config from a bookmark leaves no entry of ours
  // behind, and history.back() would walk out of the app.
  it("goes home instead when there is nothing of ours to go back to", async () => {
    const back = vi.spyOn(window.history, "back").mockImplementation(() => {});
    activeView.set("management");
    render(SidebarHeader);

    await fireEvent.click(screen.getByText("Terug"));

    expect(back).not.toHaveBeenCalled();
    expect(get(activeView)).toBe("home");
  });
});
