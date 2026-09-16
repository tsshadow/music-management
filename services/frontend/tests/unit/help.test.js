import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import Help from "../../src/lib/settings/Help.svelte";
import { HELP_SECTIONS, paragraphsOf, sectionsFor } from "../../src/lib/help.js";
import { viewToPath } from "../../src/lib/router.js";
import { mumaUser } from "../../src/lib/store.js";
import { platform } from "../../src/lib/platform/index.js";
import nl from "../../src/lib/i18n/locales/nl.json";
import en from "../../src/lib/i18n/locales/en.json";

describe("help sections", () => {
  it("have unique ids and text in both languages", () => {
    const ids = HELP_SECTIONS.map((section) => section.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const id of ids) {
      for (const dictionary of [nl, en]) {
        expect(dictionary.help[id]?.title, `${id} title`).toBeTruthy();
        expect(dictionary.help[id]?.body, `${id} body`).toBeTruthy();
      }
    }
  });

  it("point at views that exist", () => {
    for (const section of HELP_SECTIONS) {
      if (section.view) expect(viewToPath({ view: section.view }), section.id).not.toBeNull();
    }
  });

  it("keep the phone-only and admin-only sections for those readers", () => {
    const everyone = sectionsFor().map((s) => s.id);
    expect(everyone).not.toContain("downloads");
    expect(everyone).not.toContain("management");
    expect(sectionsFor({ native: true }).map((s) => s.id)).toContain("car");
    expect(sectionsFor({ admin: true }).map((s) => s.id)).toContain("management");
  });

  it("split a body on blank lines", () => {
    expect(paragraphsOf("Eén.\n\nTwee.\n")).toEqual(["Eén.", "Twee."]);
    expect(paragraphsOf(undefined)).toEqual([]);
  });
});

describe("Help page", () => {
  beforeEach(() => {
    mumaUser.set(null);
    platform.system.isNative = false;
  });

  it("renders every section for a listener in a browser", () => {
    render(Help, { onnavigate: vi.fn() });

    expect(screen.getByRole("heading", { name: "Nummers en sets" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Carmodus" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Beheer" })).toBeNull();
  });

  it("adds the phone and admin sections when they apply", () => {
    platform.system.isNative = true;
    mumaUser.set({ is_admin: true });
    try {
      render(Help, { onnavigate: vi.fn() });

      expect(screen.getByRole("heading", { name: "Carmodus" })).toBeTruthy();
      expect(screen.getByRole("heading", { name: "Beheer" })).toBeTruthy();
    } finally {
      platform.system.isNative = false;
      mumaUser.set(null);
    }
  });

  it("takes the reader to the place a section is about", async () => {
    const onnavigate = vi.fn();
    render(Help, { onnavigate });

    await fireEvent.click(screen.getByRole("button", { name: "Naar Memories" }));

    expect(onnavigate).toHaveBeenCalledWith("memories");
  });

  it("starts the tour again on request", async () => {
    const onnavigate = vi.fn();
    render(Help, { onnavigate });

    await fireEvent.click(screen.getByRole("button", { name: "Opnieuw doorlopen" }));

    expect(onnavigate).toHaveBeenCalledWith("setup");
  });
});
