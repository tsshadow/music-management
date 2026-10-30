import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/svelte";
import UserRequestsTab from "../../src/lib/management/tabs/UserRequestsTab.svelte";
import { userPermissions, mumaUser } from "../../src/lib/store.js";

const PENDING = {
  id: 7,
  display_name: "Demo-User",
  email: "demo-user@example.org",
  avatar_url: null,
  status: "pending",
  requested_at: "2026-01-01T01:00:00Z",
  reviewed_at: null,
  reviewed_by_user_id: null,
};

const APPROVED = {
  ...PENDING,
  id: 8,
  status: "approved",
  reviewed_at: "2026-01-02T01:00:00Z",
  reviewed_by_user_id: 1,
  linked_existing: false,
};

function props(overrides = {}) {
  return {
    API_BASE: "http://muma",
    getHeaders: (extra = {}) => ({ "x-api-key": "key", ...extra }),
    onMessage: vi.fn(),
    onError: vi.fn(),
    users: [{ id: 5, username: "demo-user", display_name: "Demo S" }],
    ...overrides,
  };
}

/** Answers the list request, and whatever the review actions send. */
function mockApi({ requests = [PENDING], actionOk = true, detail = "Niet toegestaan" } = {}) {
  return vi.fn(async (_url, options = {}) => {
    if (!options.method) return { ok: true, json: async () => requests };
    return { ok: actionOk, json: async () => ({ detail }) };
  });
}

async function renderLoaded(overrides = {}) {
  const rendered = render(UserRequestsTab, props(overrides));
  await waitFor(() => expect(screen.getByText("Demo-User")).toBeTruthy());
  return rendered;
}

describe("UserRequestsTab", () => {
  beforeEach(() => {
    userPermissions.set([
      "user-requests.read",
      "user-requests.approve",
      "user-requests.reject",
      "user-requests.unapprove",
    ]);
    mumaUser.set({ id: 1, username: "admin", is_admin: false });
    globalThis.fetch = mockApi();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads the pending requests first", async () => {
    await renderLoaded();

    expect(globalThis.fetch).toHaveBeenCalledWith("http://muma/api/user-requests?status=pending", {
      headers: { "x-api-key": "key" },
    });
    expect(screen.getByText("demo-user@example.org")).toBeTruthy();
  });

  it("says so when there is nothing waiting", async () => {
    globalThis.fetch = mockApi({ requests: [] });

    render(UserRequestsTab, props());

    await waitFor(() =>
      expect(screen.getByText("Geen verzoeken gevonden met status 'pending'.")).toBeTruthy(),
    );
  });

  it("reports a list that could not be loaded", async () => {
    globalThis.fetch = vi.fn(async () => ({ ok: false, json: async () => ({}) }));
    const onError = vi.fn();

    render(UserRequestsTab, props({ onError }));

    await waitFor(() =>
      expect(onError).toHaveBeenCalledWith("Kon toegangsverzoeken niet ophalen."),
    );
  });

  it("reports a list request that never arrived", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("network down");
    });
    const onError = vi.fn();

    render(UserRequestsTab, props({ onError }));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Netwerkfout bij ophalen verzoeken."));
  });

  it("switching the filter reloads with that status", async () => {
    await renderLoaded();

    await fireEvent.click(screen.getByText("Goedgekeurd"));

    await waitFor(() =>
      expect(globalThis.fetch).toHaveBeenCalledWith(
        "http://muma/api/user-requests?status=approved",
        { headers: { "x-api-key": "key" } },
      ),
    );
  });

  it("shows who reviewed a request once it is no longer pending", async () => {
    globalThis.fetch = mockApi({ requests: [APPROVED] });
    render(UserRequestsTab, props());
    await waitFor(() => expect(screen.getByText("Demo-User")).toBeTruthy());

    await fireEvent.click(screen.getByText("Goedgekeurd"));

    await waitFor(() => expect(screen.getByText("1")).toBeTruthy());
  });

  it("approving asks for confirmation before anything is sent", async () => {
    await renderLoaded();
    globalThis.fetch.mockClear();

    await fireEvent.click(screen.getByText("Goedkeuren"));

    expect(screen.getByText(/Weet je zeker/)).toBeTruthy();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("a confirmed approval creates a new account by default", async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });
    await fireEvent.click(screen.getByText("Goedkeuren"));

    await fireEvent.click(screen.getByText("Bevestig goedkeuring"));

    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith("Verzoek van Demo-User goedgekeurd!"),
    );
    const [url, options] = globalThis.fetch.mock.calls.find(([, o]) => o?.method === "POST");
    expect(url).toBe("http://muma/api/user-requests/7/approve");
    expect(JSON.parse(options.body)).toEqual({ link_user_id: null, display_name: null });
  });

  it("an approval can link the identity to an existing account", async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });
    await fireEvent.click(screen.getByText("Goedkeuren"));

    await fireEvent.change(screen.getByLabelText(/dezelfde persoon/i), { target: { value: "5" } });
    await fireEvent.click(screen.getByText("Bevestig goedkeuring"));

    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith(
        "Verzoek van Demo-User gekoppeld aan bestaand account!",
      ),
    );
    const [, options] = globalThis.fetch.mock.calls.find(([, o]) => o?.method === "POST");
    expect(JSON.parse(options.body).link_user_id).toBe(5);
  });

  it("an approval can override the display name", async () => {
    await renderLoaded();
    await fireEvent.click(screen.getByText("Goedkeuren"));

    await fireEvent.input(screen.getByLabelText(/Weergavenaam/i), { target: { value: "Demo S" } });
    await fireEvent.click(screen.getByText("Bevestig goedkeuring"));

    await waitFor(() => {
      const [, options] = globalThis.fetch.mock.calls.find(([, o]) => o?.method === "POST");
      expect(JSON.parse(options.body).display_name).toBe("Demo S");
    });
  });

  it("reports the reason an approval was refused", async () => {
    globalThis.fetch = mockApi({ actionOk: false, detail: "Al gekoppeld" });
    const onError = vi.fn();
    await renderLoaded({ onError });
    await fireEvent.click(screen.getByText("Goedkeuren"));

    await fireEvent.click(screen.getByText("Bevestig goedkeuring"));

    await waitFor(() => expect(onError).toHaveBeenCalledWith("Al gekoppeld"));
  });

  it("rejecting sends the rejection once confirmed", async () => {
    const onMessage = vi.fn();
    await renderLoaded({ onMessage });

    await fireEvent.click(screen.getByText("Afwijzen"));
    await fireEvent.click(screen.getByText("Bevestig afwijzing"));

    await waitFor(() => expect(onMessage).toHaveBeenCalledWith("Verzoek van Demo-User afgewezen."));
    const [url] = globalThis.fetch.mock.calls.find(([, o]) => o?.method === "POST");
    expect(url).toBe("http://muma/api/user-requests/7/reject");
  });

  it("undoing an approval sends the unapprove once confirmed", async () => {
    globalThis.fetch = mockApi({ requests: [APPROVED] });
    const onMessage = vi.fn();
    render(UserRequestsTab, props({ onMessage }));
    await waitFor(() => expect(screen.getByText("Demo-User")).toBeTruthy());
    await fireEvent.click(screen.getByText("Goedgekeurd"));

    await waitFor(() => expect(screen.getByText("Ongedaan maken")).toBeTruthy());
    await fireEvent.click(screen.getByText("Ongedaan maken"));
    await fireEvent.click(screen.getByText("Bevestig ongedaan maken"));

    await waitFor(() =>
      expect(onMessage).toHaveBeenCalledWith("Goedkeuring van Demo-User ongedaan gemaakt."),
    );
  });

  it("cancelling closes the dialog without sending anything", async () => {
    await renderLoaded();
    await fireEvent.click(screen.getByText("Goedkeuren"));
    globalThis.fetch.mockClear();

    await fireEvent.click(screen.getByText("Annuleren"));

    expect(screen.queryByText("Bevestig goedkeuring")).toBeNull();
    expect(globalThis.fetch).not.toHaveBeenCalled();
  });

  it("a reviewer without the approve permission is not offered the button", async () => {
    userPermissions.set(["user-requests.read"]);

    await renderLoaded();

    expect(screen.queryByText("Goedkeuren")).toBeNull();
    expect(screen.queryByText("Afwijzen")).toBeNull();
  });

  it("an admin is offered every action regardless of the permission list", async () => {
    userPermissions.set([]);
    mumaUser.set({ id: 1, username: "admin", is_admin: true });

    await renderLoaded();

    expect(screen.getByText("Goedkeuren")).toBeTruthy();
  });
});
