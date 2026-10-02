import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import UsersTab from "../../src/lib/management/tabs/UsersTab.svelte";
import { credentials, mumaUser, userPermissions, subsonicToken } from "../../src/lib/store.js";

/**
 * Deleting an account from Beheer > Gebruikers (issue #38): DELETE /api/users/{id} takes
 * `users.update`, the button follows that permission, and a refusal shows the server's reason --
 * the last-admin guard of bug report 052 says why, which "could not delete" does not.
 */

const USER = { id: 7, username: "lisa", display_name: "Lisa", enabled: true, role_name: "user" };

function props(overrides = {}) {
  return {
    users: [USER],
    roles: [{ id: 1, name: "user" }],
    selectedUser: null,
    API_BASE: "/muma",
    getHeaders: (extra = {}) => ({ ...extra, "X-API-Key": "k" }),
    fetchUsers: vi.fn(),
    onMessage: vi.fn(),
    onError: vi.fn(),
    onSelectUser: vi.fn(),
    navigateToScrobbleImport: () => {},
    ...overrides,
  };
}

/** Answers the DELETE with `status` and `body`; everything else with an empty 200. */
function mockDelete(status, body) {
  return vi.fn(async (url, options = {}) => {
    if (options.method === "DELETE") {
      return { ok: status < 300, status, json: async () => body, text: async () => "" };
    }
    return { ok: true, json: async () => ({}), text: async () => "" };
  });
}

describe("UsersTab -- deleting an account", () => {
  beforeEach(() => {
    credentials.set({ url: "", username: "user" });
    subsonicToken.set({ username: "user", token: "t" });
    mumaUser.set({ id: 1, is_admin: true, role_name: "admin" });
    userPermissions.set(["users.update"]);
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("shows the server's reason when the delete is refused", async () => {
    globalThis.fetch = mockDelete(409, {
      detail: "De laatste beheerder kan niet worden verwijderd",
    });
    const onError = vi.fn();
    render(UsersTab, props({ onError }));

    await fireEvent.click(screen.getByTitle("Verwijder gebruiker"));

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith("De laatste beheerder kan niet worden verwijderd"),
    );
  });

  it("falls back to the generic message when the server gives no reason", async () => {
    globalThis.fetch = mockDelete(500, {});
    const onError = vi.fn();
    render(UsersTab, props({ onError }));

    await fireEvent.click(screen.getByTitle("Verwijder gebruiker"));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Kon gebruiker niet verwijderen."));
  });

  it("offers no delete without users.update", () => {
    mumaUser.set({ id: 7, is_admin: false, role_name: "user" });
    userPermissions.set([]);
    globalThis.fetch = mockDelete(200, {});
    render(UsersTab, props());

    expect(screen.getByTitle("Verwijder gebruiker").disabled).toBe(true);
  });
});
