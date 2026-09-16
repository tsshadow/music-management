/**
 * Helpers for the festivals tab: the pure data between the form and the API.
 *
 * The validation mirrors what `/api/rules/festivals` enforces (a name, ISO dates,
 * plausible years), so a disabled Save and a rejected request agree.
 */

const DATE = /^\d{4}-\d{2}-\d{2}$/;
export const YEAR_MIN = 1980;
export const YEAR_MAX = 2049;

/** A blank form, also what "Nieuw festival" opens with. */
export function emptyFestival() {
  return { id: null, name: "", active: true, aliases: [], editions: [] };
}

/**
 * The form state for an existing row: aliases as one-per-line text, editions as
 * editable rows, so the form never holds a shape the API would not understand.
 *
 * @param {Object} row
 * @returns {Object}
 */
export function formFrom(row) {
  return {
    id: row?.id ?? null,
    name: row?.name ?? "",
    active: row?.active !== false,
    aliasText: (row?.aliases ?? []).join("\n"),
    editions: (row?.editions ?? []).map((edition) => ({
      year: String(edition.year ?? ""),
      date: edition.date ?? "",
    })),
  };
}

/**
 * Validate a form and build the request body for it.
 *
 * @param {Object} form - As {@link formFrom} returns it.
 * @returns {{valid: boolean, error: string|null, payload?: Object}} `error` is an i18n key.
 */
export function buildFestival(form) {
  const name = String(form?.name ?? "").trim();
  if (!name) return { valid: false, error: "management.festivals.errorName" };
  const aliases = [];
  for (const line of String(form?.aliasText ?? "").split("\n")) {
    const alias = line.trim();
    if (alias && !aliases.some((existing) => existing.toLowerCase() === alias.toLowerCase())) {
      aliases.push(alias);
    }
  }
  const editions = [];
  for (const edition of form?.editions ?? []) {
    const year = Number(String(edition.year ?? "").trim());
    const date = String(edition.date ?? "").trim();
    if (!year && !date) continue;
    if (!Number.isInteger(year) || year < YEAR_MIN || year > YEAR_MAX) {
      return { valid: false, error: "management.festivals.errorYear" };
    }
    if (!DATE.test(date) || Number.isNaN(Date.parse(date))) {
      return { valid: false, error: "management.festivals.errorDate" };
    }
    if (editions.some((existing) => existing.year === year)) {
      return { valid: false, error: "management.festivals.errorDuplicateYear" };
    }
    editions.push({ year, date });
  }
  editions.sort((a, b) => a.year - b.year);
  return {
    valid: true,
    error: null,
    payload: { name, active: form.active !== false, aliases, editions },
  };
}

/** Rows whose name or any alias contains the query, case-insensitively. */
export function filterFestivals(rows, query) {
  const needle = String(query ?? "")
    .trim()
    .toLowerCase();
  if (!needle) return rows;
  return rows.filter(
    (row) =>
      row.name.toLowerCase().includes(needle) ||
      (row.aliases ?? []).some((alias) => alias.toLowerCase().includes(needle)),
  );
}
