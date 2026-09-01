/**
 * What a radio channel's filter means, kept out of the components.
 *
 * A channel is a stored library filter (see docs/radio-mode.md): the management
 * screen edits one, the player describes one, and both need the same rules about
 * which fields count as set. Everything here is pure so it can be tested without
 * a DOM.
 */

/** The rating a track needs before it counts as a favourite. */
export const MAX_RATING = 5;

/** Empty form fields, as the editor binds them: strings, because inputs are strings. */
export function emptyFilterForm() {
  return {
    label: "",
    genre: "",
    artist: "",
    length: "",
    year: "",
    rating_min: "",
    rating_max: "",
    duration_min: "",
    duration_max: "",
    include_unrated: false,
  };
}

const NUMERIC_FIELDS = ["rating_min", "rating_max", "duration_min", "duration_max"];
const TEXT_FIELDS = ["label", "genre", "artist", "length", "year"];

/** Turn a stored filter back into form fields. */
export function filterToForm(filter) {
  const form = emptyFilterForm();
  for (const [key, value] of Object.entries(filter || {})) {
    if (key === "include_unrated") form.include_unrated = Boolean(value);
    else if (key in form) form[key] = value === null || value === undefined ? "" : String(value);
  }
  return form;
}

/**
 * Turn form fields into the payload the API stores.
 *
 * Blank means "do not filter on this", which is why empty strings are dropped
 * rather than sent as empty values -- an empty payload is a channel that plays
 * the whole library.
 */
export function formToFilter(form) {
  const filter = {};
  for (const field of TEXT_FIELDS) {
    const value = (form?.[field] ?? "").trim();
    if (value) filter[field] = value;
  }
  for (const field of NUMERIC_FIELDS) {
    const raw = form?.[field];
    if (raw === "" || raw === null || raw === undefined) continue;
    const value = Number(raw);
    if (Number.isFinite(value)) filter[field] = value;
  }
  // Only meaningful next to a rating bound, so it never travels on its own.
  if (form?.include_unrated && ("rating_min" in filter || "rating_max" in filter)) {
    filter.include_unrated = true;
  }
  return filter;
}

function formatDuration(seconds) {
  const total = Math.max(0, Math.round(seconds));
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, "0")}`;
}

/**
 * A one-line summary of what a channel plays, for a list row or a player label.
 *
 * Deliberately built from the filter's own values -- label, genre and artist
 * names are proper nouns in every language -- with only symbols around them.
 *
 * @param {object} filter
 * @param {string} [emptyLabel] - what to say when nothing is filtered on.
 */
export function describeFilter(filter, emptyLabel = "") {
  const parts = [];
  for (const field of ["label", "genre", "artist", "year", "length"]) {
    const value = (filter?.[field] ?? "").toString().trim();
    if (value) parts.push(value);
  }

  const min = filter?.duration_min;
  const max = filter?.duration_max;
  if (Number.isFinite(min) && Number.isFinite(max))
    parts.push(`${formatDuration(min)}–${formatDuration(max)}`);
  else if (Number.isFinite(min)) parts.push(`≥ ${formatDuration(min)}`);
  else if (Number.isFinite(max)) parts.push(`≤ ${formatDuration(max)}`);

  const ratingMin = filter?.rating_min;
  const ratingMax = filter?.rating_max;
  if (Number.isFinite(ratingMin) && ratingMin > 0) {
    parts.push(ratingMin >= MAX_RATING ? `${MAX_RATING}★` : `${ratingMin}★+`);
  } else if (Number.isFinite(ratingMax)) {
    parts.push(`≤ ${ratingMax}★`);
  }

  return parts.length ? parts.join(" · ") : emptyLabel;
}

/** A slug the API will accept, derived from what the user typed as a name. */
export function slugify(name) {
  return (name || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

/**
 * Which channel to tune into: the one asked for, else the first on offer.
 *
 * @param {Array<{slug: string}>} channels
 * @param {string} [preferredSlug]
 */
export function chooseChannel(channels, preferredSlug) {
  const list = channels || [];
  if (preferredSlug) {
    const match = list.find((channel) => channel.slug === preferredSlug);
    if (match) return match;
  }
  return list[0] || null;
}
