/**
 * Which tags the media scanner indexes, so a browse page can tell "nothing tagged
 * that yet" apart from "this tag was never scanned".
 *
 * The two look identical from `getTags`: an unknown cluster type and a type with no
 * clusters both come back as an empty list. The difference is only visible in the
 * scanner's settings, which ride along on `getScanStatus` -- and only for an admin.
 */

/**
 * Reads the scanner's extra tags.
 *
 * @param {string} authParams - The query string carrying the session, as built by
 *   the `authParams` store. Empty before login.
 * @returns {Promise<string[]|null>} The indexed tag names, or null when they cannot
 *   be known: no session, a non-admin (whose response carries no settings at all), an
 *   older server, or a failed request. Null means "no hint available" -- never treat
 *   it as an empty list, or every listener gets an administrator's diagnostic.
 */
export async function loadIndexedTags(authParams) {
  if (!authParams) return null;

  try {
    const response = await fetch(`/rest/getScanStatus?${authParams}`);
    if (!response.ok) return null;

    const data = await response.json();
    const settings = data['subsonic-response']?.scanStatus?.scanSettings;
    if (!settings) return null;

    const value = settings.extraTagsToScan?.value;
    if (value === undefined || value === null) return null;

    return Array.isArray(value) ? value : [value];
  } catch (e) {
    console.error('Failed to read the scanner settings:', e);
    return null;
  }
}
