import { render, screen, waitFor, fireEvent } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ConfigTab from "../../src/lib/management/tabs/ConfigTab.svelte";
import { SECRET_SENTINEL } from "../../src/lib/management/configFields.js";

const FIELDS = [
  {
    key: "max_retag_files",
    type: "integer",
    group: "Tagger",
    secret: false,
    description: "Ceiling on one apply-now.",
    default: 2000,
    value: 2000,
    nullable: true,
  },
  {
    key: "db_pass",
    type: "string",
    group: "Database",
    secret: true,
    description: "Database password.",
    default: "",
    value: SECRET_SENTINEL,
    nullable: true,
  },
  {
    key: "db_user",
    type: "string",
    group: "Database",
    secret: false,
    description: "Database user.",
    default: "",
    value: "muma",
    nullable: true,
  },
];

function api({ fields = FIELDS, saveOk = true } = {}) {
  return vi.fn(async (url, options) => {
    if (url.includes("/api/config/fields")) {
      return { ok: true, status: 200, json: async () => fields };
    }
    if (url.includes("/api/config/") && options?.method === "POST") {
      return { ok: saveOk, status: saveOk ? 200 : 400, json: async () => ({ detail: "nope" }) };
    }
    return { ok: true, status: 200, json: async () => ({}) };
  });
}

const props = (over = {}) => ({
  API_BASE: "http://muma",
  getHeaders: (extra = {}) => ({ ...extra }),
  onMessage: vi.fn(),
  onError: vi.fn(),
  ...over,
});

beforeEach(() => {
  globalThis.fetch = api();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("ConfigTab", () => {
  it("renders the schema grouped, so related settings sit together", async () => {
    render(ConfigTab, props());
    await waitFor(() => expect(screen.getByText("Tagger")).toBeTruthy());
    expect(screen.getByText("Database")).toBeTruthy();
    expect(screen.getByText("max_retag_files")).toBeTruthy();
  });

  it("shows a field description, because a key alone does not explain itself", async () => {
    render(ConfigTab, props());
    await waitFor(() => expect(screen.getByText("Ceiling on one apply-now.")).toBeTruthy());
  });

  it("says a secret is set without showing what it is", async () => {
    render(ConfigTab, props());
    await waitFor(() => expect(screen.getByText("db_pass")).toBeTruthy());
    const input = document.getElementById("cfg-db_pass");
    expect(input.type).toBe("password");
    expect(input.value).toBe(SECRET_SENTINEL);
  });

  it("shows a read-only field disabled, with where its value comes from", async () => {
    const fields = [
      ...FIELDS,
      {
        key: "db_host",
        type: "string",
        group: "Database",
        secret: false,
        read_only: true,
        description: "Database host.",
        default: "",
        value: "mariadb",
        nullable: true,
      },
    ];
    globalThis.fetch = api({ fields });
    render(ConfigTab, props());
    await waitFor(() => expect(screen.getByText("db_host")).toBeTruthy());
    const input = document.getElementById("cfg-db_host");
    expect(input.disabled).toBe(true);
    expect(input.value).toBe("mariadb");
    expect(screen.getByText(/Alleen-lezen/)).toBeTruthy();
    expect(document.getElementById("cfg-db_user").disabled).toBe(false);
  });

  it("has nothing to save until something changes", async () => {
    render(ConfigTab, props());
    await waitFor(() => expect(screen.getByText("max_retag_files")).toBeTruthy());
    expect(screen.getByText("Opslaan").closest("button").disabled).toBe(true);
  });

  it("sends only the edited field, leaving the untouched secret out", async () => {
    render(ConfigTab, props());
    await waitFor(() => expect(screen.getByText("max_retag_files")).toBeTruthy());

    await fireEvent.input(document.getElementById("cfg-max_retag_files"), {
      target: { value: "50" },
    });
    await waitFor(() => expect(screen.getByText("1 opslaan")).toBeTruthy());
    await fireEvent.click(screen.getByText("1 opslaan").closest("button"));

    const post = globalThis.fetch.mock.calls.find(([, options]) => options?.method === "POST");
    expect(JSON.parse(post[1].body)).toEqual({ updates: { max_retag_files: 50 } });
  });

  it("does send a secret the user retyped", async () => {
    render(ConfigTab, props());
    await waitFor(() => expect(screen.getByText("db_pass")).toBeTruthy());

    await fireEvent.input(document.getElementById("cfg-db_pass"), { target: { value: "hunter2" } });
    await waitFor(() => expect(screen.getByText("1 opslaan")).toBeTruthy());
    await fireEvent.click(screen.getByText("1 opslaan").closest("button"));

    const post = globalThis.fetch.mock.calls.find(([, options]) => options?.method === "POST");
    expect(JSON.parse(post[1].body)).toEqual({ updates: { db_pass: "hunter2" } });
  });

  it("explains a 403 rather than showing an empty page", async () => {
    const onError = vi.fn();
    globalThis.fetch = vi.fn(async () => ({ ok: false, status: 403, json: async () => ({}) }));
    render(ConfigTab, props({ onError }));
    await waitFor(() => expect(onError).toHaveBeenCalled());
    expect(onError.mock.calls[0][0]).toMatch(/rechten/);
  });
});
