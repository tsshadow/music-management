import { describe, it, expect, afterEach } from "vitest";
import { get } from "svelte/store";
import {
  format,
  formatDate,
  formatDateTime,
  formatNumber,
  setLocaleFromAccount,
} from "../../src/lib/i18n/index.js";

/** Locale-aware number and date formatting (bug report 083). */
describe("i18n formatters", () => {
  afterEach(() => setLocaleFromAccount("nl"));

  it("groups digits the way the locale does", () => {
    expect(formatNumber(1234567, "en")).toBe("1,234,567");
    expect(formatNumber(1234567, "nl")).toBe("1.234.567");
  });

  it("formats the dialects as Dutch, which Intl knows and they are not", () => {
    expect(formatNumber(1234, "sallands")).toBe("1.234");
    expect(formatNumber(1234, "brabants")).toBe("1.234");
  });

  it("counts a missing value as zero", () => {
    expect(formatNumber(null, "en")).toBe("0");
    expect(formatNumber(undefined, "nl")).toBe("0");
  });

  it("accepts MariaDB's space-separated timestamps", () => {
    expect(formatDate("2026-09-25 14:30:00", "en")).toBe("9/25/2026");
    expect(formatDate("2026-09-25 14:30:00", "nl")).toBe("25-9-2026");
    expect(formatDateTime("2026-09-25 14:30:00", "nl")).toContain("14:30:00");
  });

  it("follows the active locale through the store", () => {
    setLocaleFromAccount("en");
    expect(get(format).number(1234)).toBe("1,234");
    setLocaleFromAccount("nl");
    expect(get(format).number(1234)).toBe("1.234");
    expect(formatNumber(1234)).toBe("1.234");
  });
});
