import { describe, it, expect } from 'vitest';
import {
  MANAGEMENT_TABS, SETTINGS_TABS, pathToState, viewToPath
} from '../../src/lib/router.js';

/** The state object App keeps in its stores, with only the fields a route uses. */
function state(view, extra = {}) {
  return { view, loggedIn: true, ...extra };
}

describe('viewToPath', () => {
  it('sends a visitor without a session to the login screen', () => {
    expect(viewToPath({ view: 'songs', loggedIn: false })).toBe('/login');
  });

  it('maps the home view to the root path', () => {
    expect(viewToPath(state('home'))).toBe('/');
  });

  it.each([
    ['songs', '/songs'],
    ['sets', '/sets'],
    ['albums', '/albums'],
    ['genres', '/genres'],
    ['labels', '/labels'],
    ['podcasts', '/podcasts'],
    ['artists', '/artists'],
    ['playlists', '/playlists'],
    ['memories', '/memories'],
    ['history', '/history'],
    ['starred', '/starred']
  ])('maps the %s sidebar page to %s', (view, path) => {
    expect(viewToPath(state(view))).toBe(path);
  });

  it('percent-encodes a genre name so a slash in it cannot change the route', () => {
    expect(viewToPath(state('genre:Drum & Bass / UK'))).toBe('/genre/Drum%20%26%20Bass%20%2F%20UK');
  });

  it('percent-encodes a label name the same way', () => {
    expect(viewToPath(state('label:Drum & Bass / UK'))).toBe('/label/Drum%20%26%20Bass%20%2F%20UK');
  });

  it('percent-encodes a show name, which can hold a slash and a hash', () => {
    expect(viewToPath(state('podcast:Q-dance Radio / #40'))).toBe('/podcast/Q-dance%20Radio%20%2F%20%2340');
  });

  it('puts the artist id in the path', () => {
    expect(viewToPath(state('artist:ar-123'))).toBe('/artist/ar-123');
  });

  it('puts the album id in the path', () => {
    expect(viewToPath(state('album:al-456'))).toBe('/album/al-456');
  });

  it('puts the id of the open playlist in the path', () => {
    expect(viewToPath(state('playlist-detail', { playlistId: 'pl-7' }))).toBe('/playlist/pl-7');
  });

  it('leaves the URL alone while an opening playlist has no id yet', () => {
    expect(viewToPath(state('playlist-detail'))).toBeNull();
  });

  it('percent-encodes a search query', () => {
    expect(viewToPath(state('search:drum & bass'))).toBe('/search/drum%20%26%20bass');
  });

  it('names the open settings tab in the path', () => {
    expect(viewToPath(state('settings', { settingsTab: 'advanced' }))).toBe('/settings/advanced');
  });

  it('names the open management tab in the path', () => {
    expect(viewToPath(state('management', { managementTab: 'scanner' }))).toBe('/management/scanner');
  });

  it('leaves an unknown settings tab out of the path', () => {
    expect(viewToPath(state('settings', { settingsTab: 'scan-settings' }))).toBe('/settings');
  });

  it('leaves an unknown management tab out of the path', () => {
    expect(viewToPath(state('management', { managementTab: 'nope' }))).toBe('/management');
  });

  it('leaves the URL alone for a view that has no route', () => {
    expect(viewToPath(state('some-future-view'))).toBeNull();
  });
});

describe('pathToState', () => {
  it('reads the root path as the home view', () => {
    expect(pathToState('/')).toEqual({ view: 'home' });
  });

  it('reads an empty path as the home view', () => {
    expect(pathToState('')).toEqual({ view: 'home' });
  });

  it('reads the login path', () => {
    expect(pathToState('/login')).toEqual({ view: 'login' });
  });

  it('falls back to home for a path that matches no route', () => {
    expect(pathToState('/nope/nope')).toEqual({ view: 'home' });
  });

  it('decodes a genre name back out of the path', () => {
    expect(pathToState('/genre/Drum%20%26%20Bass%20%2F%20UK')).toEqual({ view: 'genre:Drum & Bass / UK' });
  });

  it('decodes a search query back out of the path', () => {
    expect(pathToState('/search/drum%20%26%20bass')).toEqual({ view: 'search:drum & bass' });
  });

  it('reads the playlist id off the path', () => {
    expect(pathToState('/playlist/pl-7')).toEqual({ view: 'playlist-detail', playlistId: 'pl-7' });
  });

  it('reads the settings tab off the path', () => {
    expect(pathToState('/settings/advanced')).toEqual({ view: 'settings', settingsTab: 'advanced' });
  });

  it('reads the management tab off the path', () => {
    expect(pathToState('/management/scanner')).toEqual({ view: 'management', managementTab: 'scanner' });
  });

  it('leaves the stored tab in place when the settings path names no tab', () => {
    expect(pathToState('/settings')).toEqual({ view: 'settings' });
  });

  it('leaves the stored tab in place when the management path names no tab', () => {
    expect(pathToState('/management')).toEqual({ view: 'management' });
  });

  it('ignores a settings tab that no longer exists rather than showing an empty screen', () => {
    expect(pathToState('/settings/scan-settings')).toEqual({ view: 'settings' });
  });

  it('ignores a management tab that no longer exists', () => {
    expect(pathToState('/management/nope')).toEqual({ view: 'management' });
  });

  it('ignores a trailing slash', () => {
    expect(pathToState('/songs/')).toEqual({ view: 'songs' });
  });
});

describe('round trip', () => {
  const paths = [
    '/', '/login', '/songs', '/sets', '/albums', '/genres', '/labels', '/podcasts', '/artists',
    '/playlists', '/memories', '/history', '/starred',
    '/genre/Drum%20%26%20Bass%20%2F%20UK', '/label/Hardcore', '/podcast/Hard%20With%20Style',
    '/artist/ar-1', '/album/al-2',
    '/playlist/pl-3', '/search/drum%20%26%20bass',
    ...SETTINGS_TABS.map((tab) => `/settings/${tab}`),
    ...MANAGEMENT_TABS.map((tab) => `/management/${tab}`)
  ];

  it.each(paths)('%s survives being parsed and rebuilt', (path) => {
    const parsed = pathToState(path);
    expect(viewToPath({ ...parsed, loggedIn: path !== '/login' })).toBe(path);
  });
});
