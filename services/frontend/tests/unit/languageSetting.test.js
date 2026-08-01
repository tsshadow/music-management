import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/svelte";
import { get } from "svelte/store";
import LanguageSetting from "../../src/lib/settings/LanguageSetting.svelte";
import { locale } from "../../src/lib/i18n";

describe("LanguageSetting", () => {
  beforeEach(() => {
    localStorage.clear();
    locale.set("en");
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
});
