/**
 * Calls the three edit pages make.
 *
 * Kept apart from the components so a page is a form plus a call, and so the error
 * shape is decided once: every write returns the parsed body on success and throws an
 * Error carrying the backend's `detail` otherwise. That detail is written to be shown
 * ("Genre 'Arts' has not been accepted by curation"), so the pages surface it as-is
 * rather than replacing it with a generic failure message.
 */
import { apiBase, getHeaders, jsonHeaders } from '../mumaApi';

async function request(path, options = {}) {
  const response = await fetch(`${apiBase()}/api/curation${path}`, options);
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) {
    throw new Error((body && body.detail) || `Request failed (${response.status})`);
  }
  return body;
}

const read = (path) => request(path, { headers: getHeaders() });
const write = (path, method, payload) => request(path, {
  method,
  headers: jsonHeaders(),
  body: payload === undefined ? undefined : JSON.stringify(payload)
});

const seg = (value) => encodeURIComponent(value);

export const loadArtist = (name) => read(`/artists/${seg(name)}`);
export const loadLabel = (name) => read(`/labels/${seg(name)}`);
export const loadGenre = (name) => read(`/genres/${seg(name)}`);

export const setArtistMbid = (name, mbid) => write(`/artists/${seg(name)}/mbid`, 'PUT', { mbid });
export const setArtistExternalId = (name, entry) => write(`/artists/${seg(name)}/external-ids`, 'PUT', entry);
export const removeArtistExternalId = (name, source) =>
  write(`/artists/${seg(name)}/external-ids/${seg(source)}`, 'DELETE');
export const addArtistAlias = (name, alias) => write(`/artists/${seg(name)}/aliases`, 'POST', { alias });
export const removeArtistAlias = (name, alias) => write(`/artists/${seg(name)}/aliases/${seg(alias)}`, 'DELETE');
export const addArtistGenre = (name, genreId) => write(`/artists/${seg(name)}/genres`, 'POST', { genre_id: genreId });
export const removeArtistGenre = (name, genreId) => write(`/artists/${seg(name)}/genres/${genreId}`, 'DELETE');

export const setLabelMbid = (name, mbid) => write(`/labels/${seg(name)}/mbid`, 'PUT', { mbid });
export const setLabelParent = (name, parentLabelId) =>
  write(`/labels/${seg(name)}/parent`, 'PUT', { parent_label_id: parentLabelId });
export const setLabelExternalId = (name, entry) => write(`/labels/${seg(name)}/external-ids`, 'PUT', entry);
export const removeLabelExternalId = (name, source) =>
  write(`/labels/${seg(name)}/external-ids/${seg(source)}`, 'DELETE');
export const addLabelGenre = (name, genreId) => write(`/labels/${seg(name)}/genres`, 'POST', { genre_id: genreId });
export const removeLabelGenre = (name, genreId) => write(`/labels/${seg(name)}/genres/${genreId}`, 'DELETE');
export const addLabelCatid = (name, catid) => write(`/labels/${seg(name)}/catids`, 'POST', { catid });
export const removeLabelCatid = (name, catid) => write(`/labels/${seg(name)}/catids/${seg(catid)}`, 'DELETE');

export const setGenreParents = (name, parents) => write(`/genres/${seg(name)}/parents`, 'PUT', { parents });

export const retag = (scope, name) => write('/retag', 'POST', { scope, name });

/** The genres a rule may point at: the ones curation has accepted. */
export async function loadWhiteGenres() {
  const response = await fetch(`${apiBase()}/api/rules/genres?state=white&limit=1000`, { headers: getHeaders() });
  if (!response.ok) throw new Error('Could not load the accepted genres');
  return response.json();
}
