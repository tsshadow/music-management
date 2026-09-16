import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { get } from "svelte/store";
import LanguageSetting from "../../src/lib/settings/LanguageSetting.svelte";
import { locale } from "../../src/lib/i18n";
import { platform } from "../../src/lib/platform/index.js";
import { mumaUser, mumaApiKey } from "../../src/lib/store";

describe("LanguageSetting", () => {
  beforeEach(() => {
    localStorage.clear();
    mumaUser.set(null);
    locale.set("en");
    platform.system.setAppLocale = vi.fn();
  });

  it("offers every shipped language, labelled in its own language", () => {
    render(LanguageSetting);
    const select = screen.getByRole("combobox");
    expect([...select.options].map((o) => o.value)).toEqual(["en", "nl", "sallands", "brabants"]);
    expect([...select.options].map((o) => o.text)).toEqual([
      "English",
      "Nederlands",
      "Sallaands",
      "Brabants",
    ]);
  });

  it("labels itself in the picked dialect", async () => {
    render(LanguageSetting);
    await fireEvent.change(screen.getByRole("combobox"), { target: { value: "sallands" } });
    expect(get(locale)).toBe("sallands");
    expect(screen.getByText("Toal")).toBeInTheDocument();
  });

  it("shows the active language as selected", () => {
    locale.set("nl");
    render(LanguageSetting);
    expect(screen.getByRole("combobox").value).toBe("nl");
  });

  it("labels itself in the active language", () => {
    locale.set("nl");
    render(LanguageSetting);
    expect(screen.getByText("Taal")).toBeInTheDocument();
  });

  it("switches the interface language when another one is picked", async () => {
    render(LanguageSetting);
    await fireEvent.change(screen.getByRole("combobox"), { target: { value: "nl" } });
    expect(get(locale)).toBe("nl");
    expect(screen.getByText("Taal")).toBeInTheDocument();
  });

  it("tells the shell which language was picked, so native chrome follows it too", async () => {
    render(LanguageSetting);
    await fireEvent.change(screen.getByRole("combobox"), { target: { value: "nl" } });
    await vi.waitFor(() => expect(platform.system.setAppLocale).toHaveBeenCalledWith("nl"));
  });

  it("has the account hold the new language before the shell reloads the page", async () => {
    // The shell applies a language by recreating its activity, which drops a debounced save
    // with the page; the account would then hand the old language straight back on reload.
    const order = [];
    global.fetch = vi.fn((_url, opts = {}) => {
      if (opts.method === "POST") {
        order.push(`save:${JSON.parse(JSON.parse(opts.body).settings).language}`);
        return Promise.resolve({ ok: true, json: async () => ({ status: "ok" }) });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          settings: JSON.stringify({ language: "brabants" }),
          updated_at: null,
        }),
      });
    });
    platform.system.setAppLocale = vi.fn((code) => order.push(`shell:${code}`));
    mumaApiKey.set("test-api-key");
    mumaUser.set({ id: 11 });
    // Logged in and the account's own language applied, so the pick below is a real change.
    await vi.waitFor(() => expect(get(locale)).toBe("brabants"));

    render(LanguageSetting);
    await fireEvent.change(screen.getByRole("combobox"), { target: { value: "nl" } });

    await vi.waitFor(() => expect(order).toContain("shell:nl"));
    expect(order).toEqual(["save:nl", "shell:nl"]);
  });
});
