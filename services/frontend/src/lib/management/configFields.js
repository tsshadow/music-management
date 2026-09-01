/**
 * Pure logic behind the configuration tab.
 *
 * The backend describes its own settings: `GET /api/config/fields` returns every
 * field with its key, type, group, description, default, current value and whether it
 * is a secret. So the page renders a schema rather than 36 hand-written inputs, and
 * a field added in `config_store.py` appears here without touching the frontend.
 *
 * What lives here is the part worth testing without a browser: how fields group, how
 * a typed value comes back out of an input, and which of them are actually worth
 * sending on save.
 */

/**
 * What the backend sends in place of a stored secret.
 *
 * Must match `SECRET_SENTINEL` in `services/common/config_store.py`. Both sides
 * treat it as "leave this alone"; the page additionally never sends it back, so a
 * save does not depend on the two agreeing.
 */
export const SECRET_SENTINEL = "•".repeat(8);

/**
 * Fields bucketed by group, in the order the backend listed them.
 *
 * Order is the schema's order on purpose: it puts related settings together and
 * keeps the page stable across reloads, which alphabetising would not.
 *
 * @param {Array<Object>} fields
 * @returns {Array<{name: string, fields: Array<Object>}>}
 */
export function groupFields(fields) {
  const groups = [];
  const byName = new Map();
  for (const field of fields ?? []) {
    let group = byName.get(field.group);
    if (!group) {
      group = { name: field.group, fields: [] };
      byName.set(field.group, group);
      groups.push(group);
    }
    group.fields.push(field);
  }
  return groups;
}

/**
 * An input's raw value as the API should receive it.
 *
 * A number field yields a number or null — never NaN, which would serialise to
 * `null` in some paths and blow up validation in others. Strings pass through
 * untouched, spaces included: a path may legitimately end in one.
 *
 * @param {Object} field
 * @param {*} raw
 * @returns {*}
 */
export function coerceValue(field, raw) {
  if (field.type === "integer" || field.type === "number") {
    if (raw === "" || raw === null || raw === undefined) return null;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }
  if (field.type === "boolean") return Boolean(raw);
  return raw;
}

/**
 * Whether this value is a secret the user never touched.
 *
 * @param {Object} field
 * @param {*} value
 * @returns {boolean}
 */
export function isSecretPlaceholder(field, value) {
  return Boolean(field.secret) && value === SECRET_SENTINEL;
}

/**
 * The payload for `POST /api/config`: only what actually differs.
 *
 * Sending the whole page back would work — the backend ignores the sentinel — but
 * a diff keeps a save from quietly rewriting settings the user never looked at, and
 * makes the request readable in a log.
 *
 * @param {Array<Object>} fields - The schema as loaded, carrying the stored values.
 * @param {Object} draft - Key to current input value.
 * @returns {Object} Key to new value, for changed fields only.
 */
export function changedUpdates(fields, draft) {
  const updates = {};
  for (const field of fields ?? []) {
    if (!(field.key in (draft ?? {}))) continue;
    const raw = draft[field.key];
    if (isSecretPlaceholder(field, raw)) continue;
    const next = coerceValue(field, raw);
    if (next !== coerceValue(field, field.value)) {
      updates[field.key] = next;
    }
  }
  return updates;
}
