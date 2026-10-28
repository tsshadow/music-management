import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/svelte";
import { get } from "svelte/store";
import TopBar from "../../src/lib/TopBar.svelte";
import {
  activeModal,
  activeView,
  credentials,
  isMobile,
  viewMode,
  subsonicToken,
} from "../../src/lib/store.js";

function subsonic({
  serverVersion = "0.0.57",
  releases = [{ version: "0.0.57", notes: "Nieuw" }],
} = {}) {
  return vi.fn(async (url) => {
    if (url.includes("/release-notes.json")) return { ok: true, json: async () => releases };
    if (url.includes("/rest/getGenres")) {
      return { ok: true, json: async () => ({ "subsonic-response": { genres: { genre: [] } } }) };
    }
    return {
      ok: true,
      json: async () => ({ "subsonic-response": { status: "ok", serverVersion } }),
    };
  });
}

describe("TopBar", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "demo-user", password: "pw" });
    subsonicToken.set({ username: "demo-user", token: "test-subsonic-token" });
    activeView.set("home");
    activeModal.set(null);
    isMobile.set(false);
    window.localStorage.clear();
    globalThis.fetch = subsonic();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    isMobile.set(false);
  });

  it("shows the greeting on the home screen", () => {
    render(TopBar, { greeting: "Goedemiddag" });

    expect(screen.getByText("Goedemiddag")).toBeTruthy();
  });

  it("the greeting stays away on other screens", () => {
    activeView.set("albums");

    render(TopBar, { greeting: "Goedemiddag" });

    expect(screen.queryByText("Goedemiddag")).toBeNull();
  });

  // The phone's own Home already opens with the quick-access tile grid; the greeting
  // above it only cost space there, so it is desktop-only (see PhoneHome.svelte).
  it("the greeting stays away on the phone's home screen", () => {
    isMobile.set(true);

    render(TopBar, { greeting: "Goedemiddag" });

    expect(screen.queryByText("Goedemiddag")).toBeNull();
  });

  it("leaves the branding to the sidebar", () => {
    render(TopBar, { greeting: "Goedemiddag" });

    expect(screen.queryByText("MuMa")).toBeNull();
  });

  it("remembers the server version on a first visit", async () => {
    render(TopBar, { greeting: "" });

    await waitFor(() => expect(window.localStorage.getItem("lms_last_version")).toBe("0.0.57"));
    expect(get(activeModal)).toBeNull();
  });

  it("shows the release notes after the server was upgraded", async () => {
    window.localStorage.setItem("lms_last_version", "0.0.56");

    render(TopBar, { greeting: "" });

    await waitFor(() => expect(get(activeModal)?.type).toBe("release-notes"));
    expect(get(activeModal).data.releases).toHaveLength(1);
  });

  it("an unchanged version shows nothing", async () => {
    window.localStorage.setItem("lms_last_version", "0.0.57");

    render(TopBar, { greeting: "" });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(get(activeModal)).toBeNull();
  });

  it("only releases newer than the last seen one are shown", async () => {
    window.localStorage.setItem("lms_last_version", "0.0.56");
    globalThis.fetch = subsonic({
      releases: [
        { version: "0.0.55", notes: "Oud" },
        { version: "0.0.57", notes: "Nieuw" },
      ],
    });

    render(TopBar, { greeting: "" });

    await waitFor(() => expect(get(activeModal)?.type).toBe("release-notes"));
    expect(get(activeModal).data.releases.map((r) => r.version)).toEqual(["0.0.57"]);
  });

  it("a downgrade shows nothing", async () => {
    window.localStorage.setItem("lms_last_version", "0.0.58");

    render(TopBar, { greeting: "" });

    await waitFor(() => expect(globalThis.fetch).toHaveBeenCalled());
    expect(get(activeModal)).toBeNull();
  });

  it("survives a version check that never arrives", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });

    render(TopBar, { greeting: "Goedemiddag" });

    await waitFor(() => expect(screen.getByText("Goedemiddag")).toBeTruthy());
  });
});

// The phone's one-line bar: search, then the Songs/Sets mode control, then the
// profile button -- replacing the separate row `App.svelte` used to render above
// the content.
describe("TopBar on the phone", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "demo-user", password: "pw" });
    subsonicToken.set({ username: "demo-user", token: "test-subsonic-token" });
    activeModal.set(null);
    isMobile.set(true);
    viewMode.set("songs");
    window.localStorage.clear();
    globalThis.fetch = subsonic();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    isMobile.set(false);
  });

  it("shows the mode control on a phone tab", () => {
    activeView.set("home");

    render(TopBar, { greeting: "" });

    expect(screen.getByRole("group", { name: "Modus wisselen" })).toBeTruthy();
  });

  it("keeps the mode control away from settings, which has no tab of its own", () => {
    activeView.set("settings");

    render(TopBar, { greeting: "" });

    expect(screen.queryByRole("group", { name: "Modus wisselen" })).toBeNull();
  });

  it("orders the bar search, then the mode control, then the profile button", () => {
    activeView.set("home");

    const { container } = render(TopBar, { greeting: "" });

    const search = screen.getByPlaceholderText("Wat wil je luisteren?");
    const modeControl = screen.getByRole("group", { name: "Modus wisselen" });
    const profile = container.querySelector('button[aria-haspopup="true"]');

    expect(profile).toBeTruthy();
    expect(
      search.compareDocumentPosition(modeControl) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      modeControl.compareDocumentPosition(profile) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  // The advanced-search card left the top of Bladeren; a filter icon beside the search field
  // is the only way back into it now, so it has to exist exactly on that tab.
  it("offers the filter icon on the browse tab and opens the preset builder", async () => {
    activeView.set("browse");

    render(TopBar, { greeting: "" });

    const filterButton = screen.getByLabelText("Geavanceerd zoeken");
    await fireEvent.click(filterButton);

    expect(get(activeView)).toBe("new-preset");
  });

  it("keeps the filter icon off tabs that are not browse", () => {
    activeView.set("home");

    render(TopBar, { greeting: "" });

    expect(screen.queryByLabelText("Geavanceerd zoeken")).toBeNull();
  });
});

// Bug report 090: a tablet in landscape has a coarse pointer, so `isMobile` is true, while its
// width is past Tailwind's `md` -- the desktop layout. TopBar used to pick the phone bar on
// `isMobile` alone, and that bar carries `md:hidden`, so the tablet got no search box and no
// profile button at all. jsdom applies no CSS, so the test asserts the rendered branch is one the
// CSS does not hide at that width: no `md:hidden` anywhere above the search field or the button.
describe("TopBar on a tablet in landscape", () => {
  let originalMatchMedia;

  beforeEach(() => {
    originalMatchMedia = window.matchMedia;
    window.matchMedia = (query) => ({
      matches: query === "(min-width: 48rem)" || query === "(pointer: coarse)",
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    });
    credentials.set({ url: "", username: "demo-user", password: "pw" });
    subsonicToken.set({ username: "demo-user", token: "test-subsonic-token" });
    activeModal.set(null);
    activeView.set("home");
    isMobile.set(true);
    viewMode.set("songs");
    window.localStorage.clear();
    globalThis.fetch = subsonic();
  });

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
    vi.restoreAllMocks();
    isMobile.set(false);
  });

  function hiddenFromMdUp(element) {
    for (let node = element; node; node = node.parentElement) {
      if (node.classList?.contains("md:hidden")) return true;
    }
    return false;
  }

  it("renders the search field and the profile button in a bar the md layout shows", () => {
    const { container } = render(TopBar, { greeting: "Goedemiddag" });

    const search = screen.getByPlaceholderText("Wat wil je luisteren?");
    const profile = container.querySelector('button[aria-haspopup="true"]');

    expect(profile).toBeTruthy();
    expect(hiddenFromMdUp(search)).toBe(false);
    expect(hiddenFromMdUp(profile)).toBe(false);
  });

  it("uses the desktop bar there, not the phone's one-line bar", () => {
    render(TopBar, { greeting: "Goedemiddag" });

    expect(screen.getByText("Goedemiddag")).toBeTruthy();
    expect(screen.queryByRole("group", { name: "Modus wisselen" })).toBeNull();
  });
});
