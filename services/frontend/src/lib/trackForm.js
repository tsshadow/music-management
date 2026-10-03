/**
 * The forms MuMa classifies every track under (`services/common/track_form.py`), which LMS filters
 * on through the `form` parameter of `getSpotifyTracks` and `getSongs`.
 *
 * The filter bar only offers the three long forms, and only in the sets view: in the songs view
 * every row is a track, so a picker there would have one real choice. See
 * docs/designs/track-form/functional.md.
 *
 * `interview` and `preview` are the non-music forms: LMS leaves them out of every music list, and
 * no chip offers them, so the sets view never asks for one (docs/designs/non-music-forms/).
 */

export const TRACK_FORMS = Object.freeze(["track", "set", "liveset", "podcast", "interview", "preview"]);

/** The forms that are not music: talk and DVD trailers, findable through search only. */
export const NON_MUSIC_FORMS = Object.freeze(["interview", "preview"]);

/** The forms the sets view's Soort chip offers, in the order it lists them. */
export const SET_FORMS = Object.freeze(["set", "liveset", "podcast"]);

/** i18n keys naming each form. */
export const FORM_LABEL_KEYS = Object.freeze({
  track: "filter.form.track",
  set: "filter.form.set",
  liveset: "filter.form.liveset",
  podcast: "filter.form.podcast",
  interview: "filter.form.interview",
  preview: "filter.form.preview",
});

/**
 * The `form` value to send for a view, or undefined for none -- so a stale selection from the sets
 * view never narrows the songs view, and a value that is not a form (an old saved state) is not
 * sent for the server to refuse the whole request over.
 *
 * @param {string|null|undefined} form
 * @param {'songs'|'sets'} viewMode
 * @returns {string|undefined}
 */
export function formParam(form, viewMode) {
  if (viewMode !== "sets") return undefined;
  const value = String(form ?? "")
    .trim()
    .toLowerCase();
  return SET_FORMS.includes(value) ? value : undefined;
}
