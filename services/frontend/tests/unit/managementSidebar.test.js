import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { get } from "svelte/store";
import ManagementSidebar from "../../src/lib/management/ManagementSidebar.svelte";
import { activeManagementTab, mumaUser, userPermissions } from "../../src/lib/store.js";
import { MANAGEMENT_TABS } from "../../src/lib/router.js";

describe("ManagementSidebar", () => {
  beforeEach(() => {
    activeManagementTab.set("overview");
    mumaUser.set({ id: 1, username: "user", is_admin: false });
    userPermissions.set([]);
    localStorage.clear();
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("lists the entries everyone may see", () => {
    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.getByText("Overzicht")).toBeTruthy();
    expect(screen.getByText("Downloaders")).toBeTruthy();
    expect(screen.getByText("Collectie")).toBeTruthy();
    expect(screen.getByText("Curatie")).toBeTruthy();
  });

  it("the user tabs stay hidden without the permission", () => {
    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.queryByText("Gebruikers")).toBeNull();
    expect(screen.queryByText("Toegangsverzoeken")).toBeNull();
  });

  it("the user tab appears with the permission to read users", async () => {
    userPermissions.set(["users.read"]);

    render(ManagementSidebar, { onnavigate: vi.fn() });
    await fireEvent.click(screen.getByText("Toegang"));

    expect(screen.getByText("Gebruikers")).toBeTruthy();
  });

  it("the access-request tab appears with its own permission", async () => {
    userPermissions.set(["user-requests.read"]);

    render(ManagementSidebar, { onnavigate: vi.fn() });
    await fireEvent.click(screen.getByText("Toegang"));

    expect(screen.getByText("Toegangsverzoeken")).toBeTruthy();
  });

  it("an administrator sees every tab", async () => {
    mumaUser.set({ id: 1, username: "user", is_admin: true });

    render(ManagementSidebar, { onnavigate: vi.fn() });
    await fireEvent.click(screen.getByText("Toegang"));

    expect(screen.getByText("Gebruikers")).toBeTruthy();
    expect(screen.getByText("Toegangsverzoeken")).toBeTruthy();
  });

  it("picking a tab switches to it", async () => {
    render(ManagementSidebar, { onnavigate: vi.fn() });

    await fireEvent.click(screen.getByText("Downloaders"));

    expect(get(activeManagementTab)).toBe("downloaders");
  });

  it("every tab an administrator can open has a route", async () => {
    mumaUser.set({ id: 1, username: "user", is_admin: true });
    userPermissions.set(["users.read", "user-requests.read", "radio.manage"]);
    const { container } = render(ManagementSidebar, { onnavigate: vi.fn() });

    // Clicking is the only way to learn a tab's id from the outside; the
    // sidebar keeps its own list, and a tab added there but not to the routing
    // table would silently lose its URL.
    const reached = [];
    for (const button of container.querySelectorAll("nav button")) {
      await fireEvent.click(button);
      reached.push(get(activeManagementTab));
    }

    expect(reached.length).toBeGreaterThan(0);
    expect(reached.filter((tab) => !MANAGEMENT_TABS.includes(tab))).toEqual([]);
  });

  it("the tab that is open is marked as such", async () => {
    activeManagementTab.set("health");

    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.getByText("Gezondheid").className).toContain("text-white");
  });

  it("shows group headers instead of one flat list", () => {
    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.getByText("Collectie")).toBeTruthy();
    expect(screen.getByText("Curatie")).toBeTruthy();
    expect(screen.getByText("Systeem")).toBeTruthy();
    expect(screen.getByText("Instellingen")).toBeTruthy();
  });

  // The group header and a tab inside it must never read the same, which is why
  // the groups are not called Bibliotheek, Tagger and Gebruikers.
  it("never gives a group the same name as a page inside it", () => {
    userPermissions.set(["users.read", "user-requests.read", "radio.manage", "news.manage"]);

    render(ManagementSidebar, { onnavigate: vi.fn() });

    for (const name of ["Collectie", "Curatie", "Toegang", "Systeem", "Instellingen", "Kanalen"]) {
      expect(screen.getAllByText(name).length).toBe(1);
    }
  });

  it("keeps a collapsed group's pages out of the sidebar", () => {
    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.queryByText("Scanner")).toBeNull();
  });

  it("opens a group when its header is clicked", async () => {
    render(ManagementSidebar, { onnavigate: vi.fn() });

    await fireEvent.click(screen.getByText("Collectie"));

    expect(screen.getByText("Scanner")).toBeTruthy();
  });

  // A deep link into /management/scanner must not land inside a folded group.
  it("opens the group that owns the active tab", () => {
    activeManagementTab.set("scanner");

    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.getByText("Scanner")).toBeTruthy();
  });

  it("switches tab when a page inside a group is picked", async () => {
    render(ManagementSidebar, { onnavigate: vi.fn() });

    await fireEvent.click(screen.getByText("Collectie"));
    await fireEvent.click(screen.getByText("Scanner"));

    expect(get(activeManagementTab)).toBe("scanner");
  });

  it("renders a standalone entry as a page row, not a header", async () => {
    render(ManagementSidebar, { onnavigate: vi.fn() });

    await fireEvent.click(screen.getByText("Downloaders"));

    expect(get(activeManagementTab)).toBe("downloaders");
  });

  // Every page in Toegang needs a permission this user does not have, so the header
  // would open onto nothing.
  it("hides a group whose every page is hidden by permissions", () => {
    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.queryByText("Toegang")).toBeNull();
  });

  it("shows that group again as soon as one of its pages is permitted", () => {
    userPermissions.set(["users.read"]);

    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.getByText("Toegang")).toBeTruthy();
  });

  it("no longer offers the deleted tabs", () => {
    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.queryByText("Versies")).toBeNull();
    expect(screen.queryByText("Over")).toBeNull();
  });
});
