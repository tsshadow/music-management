import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import LibraryChips from "../../src/lib/LibraryChips.svelte";

describe("LibraryChips", () => {
  it("offers every section the phone's Library tab covers, in a browser", () => {
    render(LibraryChips, { activeView: "playlists", onnavigate: vi.fn() });

    for (const label of ["Afspeellijsten", "Artiesten", "Albums", "Favorieten"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });

  it("marks the current view's chip as pressed", () => {
    render(LibraryChips, { activeView: "artists", onnavigate: vi.fn() });

    expect(screen.getByRole("button", { name: "Artiesten" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Albums" })).toHaveAttribute("aria-pressed", "false");
  });

  it("reports the section a chip stands for to the parent", async () => {
    const onnavigate = vi.fn();
    render(LibraryChips, { activeView: "playlists", onnavigate });

    await fireEvent.click(screen.getByText("Favorieten"));

    expect(onnavigate).toHaveBeenCalledWith("starred");
  });

  it("defaults to the playlists chip when no view is given", () => {
    render(LibraryChips, { onnavigate: vi.fn() });

    expect(screen.getByRole("button", { name: "Afspeellijsten" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
