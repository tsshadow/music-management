import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/svelte";
import MobileNav from "../../src/lib/MobileNav.svelte";

/** One tab of the bar, by its landmark -- there is no other "Sets"/"Nummers" text here any more. */
function bar() {
  return within(screen.getByRole("navigation", { name: "Navigatiebalk" }));
}

describe("MobileNav", () => {
  it("is down to Spotify's three tabs", () => {
    render(MobileNav, { activeView: "home", onnavigate: vi.fn() });

    expect(bar().getByRole("button", { name: "Home" })).toBeTruthy();
    expect(bar().getByRole("button", { name: "Bladeren" })).toBeTruthy();
    expect(bar().getByRole("button", { name: "Favorieten" })).toBeTruthy();
  });

  it("no longer offers Songs, Sets or Management as a tab of its own", () => {
    render(MobileNav, { activeView: "home", onnavigate: vi.fn() });

    expect(bar().queryByRole("button", { name: "Nummers" })).toBeNull();
    expect(bar().queryByRole("button", { name: "Sets" })).toBeNull();
    expect(bar().queryByRole("button", { name: "Beheer" })).toBeNull();
  });

  it("reports the favorites tab's own view when it is tapped", async () => {
    const onnavigate = vi.fn();
    render(MobileNav, { activeView: "home", onnavigate });

    await fireEvent.click(bar().getByRole("button", { name: "Favorieten" }));

    expect(onnavigate).toHaveBeenCalledWith("favorites");
  });

  it("reports the search tab", async () => {
    const onnavigate = vi.fn();
    render(MobileNav, { activeView: "home", onnavigate });

    await fireEvent.click(bar().getByRole("button", { name: "Bladeren" }));

    expect(onnavigate).toHaveBeenCalledWith("browse");
  });

  it.each(["favorites", "preset:42", "new-preset", "preset-edit:42"])(
    "marks the favorites tab active on %s, not only on its default view",
    (view) => {
      render(MobileNav, { activeView: view, onnavigate: vi.fn() });

      expect(bar().getByRole("button", { name: "Favorieten" })).toHaveClass("text-white");
    },
  );

  it("keeps Browse lit on a page opened from one of its tiles", () => {
    render(MobileNav, { activeView: "genre:Hardcore", onnavigate: vi.fn() });

    expect(bar().getByRole("button", { name: "Bladeren" })).toHaveClass("text-white");
  });

  it("marks no tab active on a page outside the three", () => {
    render(MobileNav, { activeView: "settings", onnavigate: vi.fn() });

    for (const label of ["Home", "Bladeren", "Favorieten"]) {
      expect(bar().getByRole("button", { name: label })).not.toHaveClass("text-white");
    }
  });
});

it.each(["playlists", "playlist-detail", "playlist:42"])("%s activates Browse", (view) => {
  render(MobileNav, { activeView: view, onnavigate: vi.fn() });
  expect(bar().getByRole("button", { name: "Bladeren" })).toHaveClass("text-white");
  expect(bar().getByRole("button", { name: "Favorieten" })).not.toHaveClass("text-white");
});
