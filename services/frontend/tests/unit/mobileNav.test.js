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
    expect(bar().getByRole("button", { name: "Zoeken" })).toBeTruthy();
    expect(bar().getByRole("button", { name: "Bieb" })).toBeTruthy();
  });

  it("no longer offers Songs, Sets or Management as a tab of its own", () => {
    render(MobileNav, { activeView: "home", onnavigate: vi.fn() });

    expect(bar().queryByRole("button", { name: "Nummers" })).toBeNull();
    expect(bar().queryByRole("button", { name: "Sets" })).toBeNull();
    expect(bar().queryByRole("button", { name: "Beheer" })).toBeNull();
  });

  it("reports the library tab's own view when it is tapped", async () => {
    const onnavigate = vi.fn();
    render(MobileNav, { activeView: "home", onnavigate });

    await fireEvent.click(bar().getByRole("button", { name: "Bieb" }));

    expect(onnavigate).toHaveBeenCalledWith("playlists");
  });

  it("reports the search tab", async () => {
    const onnavigate = vi.fn();
    render(MobileNav, { activeView: "home", onnavigate });

    await fireEvent.click(bar().getByRole("button", { name: "Zoeken" }));

    expect(onnavigate).toHaveBeenCalledWith("search");
  });

  it.each(["playlists", "artists", "albums", "starred", "downloads"])(
    "marks the library tab active on %s, not only on its default view",
    (view) => {
      render(MobileNav, { activeView: view, onnavigate: vi.fn() });

      expect(bar().getByRole("button", { name: "Bieb" })).toHaveClass("text-white");
    },
  );

  it("marks no tab active on a pushed detail page", () => {
    render(MobileNav, { activeView: "genre:Hardcore", onnavigate: vi.fn() });

    for (const label of ["Home", "Zoeken", "Bieb"]) {
      expect(bar().getByRole("button", { name: label })).not.toHaveClass("text-white");
    }
  });
});
