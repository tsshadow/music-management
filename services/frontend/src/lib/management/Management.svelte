<script>
  import { t } from '../i18n/index.js';
  import { onDestroy, onMount } from 'svelte';
  import { RefreshCw } from '@lucide/svelte';
  import { activeManagementTab, isAdmin, mumaApiKey, mumaApiUrl, userPermissions, mumaUser, hasPermission, endLeftoverSharedKeySession, endRejectedSession } from '../store.js';
  import { getHeaders as sharedHeaders, fetchMumaJson, mapWithLimit } from '../mumaApi.js';
  import { MANAGEMENT_TABS } from '../router.js';

  // Every tab but Scrobble is its own chunk (lazyViews.js, issue #114): an admin opening
  // Beheer fetches the tab on screen, not all of them. Scrobble takes two `bind:` props, which
  // a props object cannot carry, so it stays in this chunk.
  import ScrobbleTab from './tabs/ScrobbleTab.svelte';
  import LazyView from '../LazyView.svelte';
  import { managementTabs } from '../lazyViews.js';

  // Fetch the open tab's chunk while the shell's own data is still loading, so the two
  // waits overlap instead of adding up.
  $effect(() => {
    const tab = $activeManagementTab;
    if (managementTabs.has(tab)) managementTabs.load(tab).catch(() => {});
  });

  // The active tab is persisted and can also arrive from the URL, so a name
  // that no longer exists -- a renamed tab, an old bookmark, a typo -- would
  // otherwise render an empty screen with a working sidebar next to it.
  $effect(() => {
    if (!MANAGEMENT_TABS.includes($activeManagementTab)) activeManagementTab.set('overview');
  });

  // State (using Svelte 5 runes)
  let isLoggedIn = $state(false);
  let apiKey = $state('');
  let loading = $state(true);
  let message = $state('');
  let error = $state('');

  // Data State
  let config = $state({ version: '...', phpmyadmin_url: '#' });
  let notes = $state({ release_notes: '', changelog: '' });
  let allNotes = $state({});
  let accounts = $state([]);
  let youtubeAccounts = $state([]);
  let latestImports = $state([]);
  let users = $state([]);
  let roles = $state([]);
  let playlists = $state([]);
  let containers = $state([]);
  let activity = $state({ recent_added: [], recent_tagged: [] });
  let stats = $state({
    total_tracks: 0,
    total_artists: 0,
    total_albums: 0,
    top_artists: [],
    top_genres: [],
    total_scrobbles: 0,
    match_rate: 0,
    recently_added: [],
    avg_track_duration: 0,
    total_unmatched: 0
  });

  // UI State
  let selectedUser = $state(null);
  let currentUser = $state(null);
  let lbUsername = $state('');
  let selectedServiceNotes = $state('control-center');
  let fetchProgress = $state({ active: false, total: 0, current: 0, last_artist: null, status: 'idle' });
  let imageStats = $state({ total_artists: 0, artists_with_images: 0, artists_without_images: 0 });
  let importMumaUser = $state('');
  let importLbUser = $state('');
  let isImporting = $state(false);

  const API_BASE = $derived($mumaApiUrl);

  // Both of these now live in lib/mumaApi.js, because the curation edit pages live
  // outside Management and cannot be handed them as props. They are still passed down
  // to every tab from here, so the tabs did not have to change.
  const getHeaders = sharedHeaders;

  /** Marks a call in fetchData's batch that failed, so its section keeps its default. */
  const FAILED = Symbol('failed');

  async function fetchData() {
    loading = true;
    const headers = getHeaders();
    try {
      // Fired a few at a time rather than all ten at once: they all reach MuMa
      // through the LMS proxy, which refuses a burst with a 503 instead of
      // queueing it. See MAX_PARALLEL_MUMA_CALLS in lib/mumaApi.js.
      const [configBody, notesBody, accountsBody, youtubeBody, allNotesBody, importsBody, usersBody, containersBody, activityBody, statsBody] = await mapWithLimit(
        [
          '/api/config',
          '/api/notes',
          '/api/soundcloud',
          '/api/youtube',
          '/api/all-notes',
          '/api/scrobble/import/latest',
          '/api/users',
          '/api/system/containers',
          '/api/system/activity',
          '/api/stats'
        ],
        // One refused call (a 403 on an endpoint this account may not read, a 500) must not
        // take the other nine down with it, nor be assigned as if it were data: an error body
        // in `users` or `accounts` rendered as a broken list. A failure comes back as
        // FAILED and leaves that section at its empty default.
        (path) => fetchMumaJson(`${$mumaApiUrl}${path}`, { headers }).catch((err) => {
          console.error(err);
          return FAILED;
        })
      );

      /**
       * `body` unless its call failed, else `fallback`.
       *
       * @param {any} body
       * @param {any} fallback
       */
      const loaded = (body, fallback) => (body === FAILED ? fallback : body);

      // The endpoint answers {config, groups}; the tabs below want the values map.
      // Reading the envelope as if it were flat is why the ntfy fields on the events
      // tab have always rendered empty.
      config = loaded(configBody?.config ?? configBody, config);
      notes = loaded(notesBody, notes);
      accounts = loaded(accountsBody, accounts);
      youtubeAccounts = loaded(youtubeBody, youtubeAccounts);
      allNotes = loaded(allNotesBody, allNotes);
      latestImports = loaded(importsBody, latestImports);
      users = loaded(usersBody, users);
      containers = loaded(containersBody, containers);
      activity = loaded(activityBody, activity);
      stats = loaded(statsBody, stats);

      const bodies = [configBody, notesBody, accountsBody, youtubeBody, allNotesBody, importsBody, usersBody, containersBody, activityBody, statsBody];
      // The banner is for "the Management API cannot be reached", not for one section this
      // deployment cannot answer (no Docker socket for the container list, say): that section
      // just stays empty, and its error is already in the console above.
      if (bodies.every((body) => body === FAILED)) error = $t('management.loadFailed');
    } catch (err) {
      error = $t('management.loadFailed');
      console.error(err);
    } finally {
      loading = false;
    }
  }

  async function fetchArtistImages() {
    message = $t('management.overview.fetchImagesStarting');
    try {
      const res = await fetch(`${$mumaApiUrl}/api/artists/fetch-images`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        message = $t('management.overview.fetchImagesStarted');
        startProgressPolling();
      }
    } catch {
      error = $t('management.overview.fetchImagesFailed');
    }
  }

  let progressInterval;
  function startProgressPolling() {
    if (progressInterval) clearInterval(progressInterval);
    progressInterval = setInterval(async () => {
      try {
        fetchProgress = await fetchMumaJson(`${$mumaApiUrl}/api/artists/fetch-progress`, { headers: getHeaders() });
        if (!fetchProgress.active && fetchProgress.status !== 'running') {
          clearInterval(progressInterval);
          fetchImageStats();
        }
      } catch (err) {
        console.error("Error polling progress:", err);
      }
    }, 1000);
  }

  // The poll outlives the screen otherwise: nothing stops it when the user
  // navigates away, so it keeps asking the server for image-fetch progress —
  // and keeps logging once the answers stop being useful.
  onDestroy(() => {
    if (progressInterval) clearInterval(progressInterval);
  });

  async function fetchImageStats() {
    try {
      imageStats = await fetchMumaJson(`${$mumaApiUrl}/api/artists/images/stats`, { headers: getHeaders() });
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchStats() {
    try {
      stats = await fetchMumaJson(`${$mumaApiUrl}/api/stats`, { headers: getHeaders() });
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchPlaylists() {
    if (!selectedUser) return;
    try {
      playlists = await fetchMumaJson(`${$mumaApiUrl}/api/users/${selectedUser.id}/dynamic-playlists`, { headers: getHeaders() });
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchLatestImports() {
    try {
      latestImports = await fetchMumaJson(`${$mumaApiUrl}/api/scrobble/import/latest`, { headers: getHeaders() });
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchUsers() {
    try {
      users = await fetchMumaJson(`${$mumaApiUrl}/api/users`, { headers: getHeaders() });
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchRoles() {
    try {
      roles = await fetchMumaJson(`${$mumaApiUrl}/api/roles`, { headers: getHeaders() });
    } catch (err) {
      console.error(err);
    }
  }

  async function selectUser(user) {
    selectedUser = user;
    if (user) {
      try {
        const res = await fetch(`${$mumaApiUrl}/api/users/${user.id}/listenbrainz`, {
          headers: getHeaders()
        });
        if (res.ok) {
          const lbData = await res.json();
          lbUsername = lbData.lb_username || '';
        } else {
          lbUsername = '';
        }
      } catch (err) {
        console.error(err);
      }
    }
  }

  async function refreshSystemStatus() {
    try {
      const headers = getHeaders();
      const [containerList, activityBody] = await Promise.all([
        fetchMumaJson(`${$mumaApiUrl}/api/system/containers`, { headers }),
        fetchMumaJson(`${$mumaApiUrl}/api/system/activity`, { headers })
      ]);
      containers = containerList;
      activity = activityBody;
    } catch (err) {
      console.error(err);
    }
  }

  onMount(async () => {
    // The session's own key. There is no auto-login any more: no password is stored to log in
    // with (issue #101), and a signed-in session always carries its key.
    apiKey = $mumaApiKey || '';

    if (apiKey) {
      try {
        const res = await fetch(`${$mumaApiUrl}/api/config`, {
          headers: { 'X-API-Key': apiKey }
        });
        // A persisted key the backend no longer accepts (a rotated or no-longer-resolving system
        // key, an account whose key was reissued) used to wedge this screen forever. The key is
        // permanent and there is no password to log in again with (issue #101): the session ends
        // and the login page comes back.
        if (res.status === 401 || res.status === 403) {
          endRejectedSession();
          isLoggedIn = false;
          loading = false;
          return;
        }
        if (res.ok) {
          isLoggedIn = true;
          const authRes = await fetch(`${$mumaApiUrl}/api/auth/verify`, {
            headers: { 'X-API-Key': apiKey }
          });
          if (authRes.ok) {
            const authData = await authRes.json();
            if (authData.type === 'user') {
              currentUser = authData.user;
              userPermissions.set(authData.user.permissions);
              mumaUser.set(authData.user);
              if (!selectedUser) selectedUser = currentUser;
            } else if (authData.type === 'system') {
              // A system key is a leftover from the login LMS used to answer
              // with its own shared `api-key`; no web login hands one out any
              // more. It makes nobody an administrator here: the session ends
              // and the user signs in once more, for their own key. See
              // endLeftoverSharedKeySession in store.js.
              endLeftoverSharedKeySession();
              isLoggedIn = false;
              loading = false;
              return;
            }
          }
          await fetchData();
          await fetchRoles();
          await fetchImageStats();
          startProgressPolling();
        } else {
          isLoggedIn = false;
        }
      } catch {
        isLoggedIn = false;
      }
    } else {
      isLoggedIn = false;
    }
    loading = false;
  });

  const onMessage = (m) => (message = m);
  const onError = (e) => (error = e);

  /**
   * The props one tab is rendered with. Called from the template, so everything it reads is
   * tracked and the tab gets fresh props when the shell's data changes.
   *
   * @param {string} tab
   * @returns {Record<string, any>}
   */
  function tabProps(tab) {
    const common = { API_BASE, getHeaders, onMessage, onError };
    switch (tab) {
      case 'overview':
        return { containers, activity, config, allNotes, selectedServiceNotes, notes, stats, fetchStats, fetchArtistImages };
      case 'libraries':
      case 'scanner':
        return { onMessage, onError };
      case 'images':
        return { ...common, apiKey, fetchArtistImages, fetchProgress, imageStats, refreshStats: fetchImageStats };
      case 'playlists':
        return { ...common, apiKey, users, playlists, selectedUser, fetchPlaylists, onSelectUser: selectUser };
      case 'downloaders':
        return { ...common, accounts, youtubeAccounts, refreshDownloaders: fetchData };
      case 'health':
        return { containers, activity, API_BASE, getHeaders, refreshSystemStatus };
      case 'users':
        return { ...common, users, roles, selectedUser, fetchUsers, onSelectUser: selectUser, navigateToScrobbleImport };
      case 'user-requests':
        return { ...common, users };
      case 'events':
        return { ...common, config };
      default:
        return common;
    }
  }

  function navigateToScrobbleImport(user, lbUser) {
    activeManagementTab.set('scrobble');
    importMumaUser = user;
    importLbUser = lbUser;
  }
</script>

<div class="flex flex-col gap-8 w-full h-full min-h-0 overflow-y-auto">
  {#if $isAdmin === false && !hasPermission('users.read')}
    <div class="flex items-center justify-center h-full">
      <div class="bg-muma-spotify-panel p-8 rounded-xl border border-white/5 max-w-md w-full text-center">
        <h2 class="text-2xl font-bold mb-4">{$t('management.noAccess')}</h2>
        <p class="text-muma-spotify-text mb-6">{$t('management.noAccessHelp')}</p>
      </div>
    </div>
  {:else if !isLoggedIn}
    <div class="flex items-center justify-center h-full">
      <div class="bg-muma-spotify-panel p-8 rounded-xl border border-white/5 max-w-md w-full text-center">
        <h2 class="text-2xl font-bold mb-4">{$t('management.connecting')}</h2>
        <p class="text-muma-spotify-text mb-6">{$t('management.connectFailed')}</p>
      </div>
    </div>
  {:else}
    {#if message}
      <div class="bg-brand text-black p-4 rounded-md mb-6 font-bold flex justify-between items-center">
        {message}
        <button onclick={() => message = ''}>&times;</button>
      </div>
    {/if}
    
    {#if error}
      <div class="bg-red-600 text-white p-4 rounded-md mb-6 font-bold flex justify-between items-center">
        {error}
        <button onclick={() => error = ''}>&times;</button>
      </div>
    {/if}

    {#if loading}
      <div class="flex items-center justify-center h-full py-20">
        <RefreshCw class="animate-spin text-brand" size={48} />
      </div>
    {:else}
      {#if $activeManagementTab === 'scrobble'}
        <ScrobbleTab 
          {API_BASE} getHeaders={getHeaders} 
          {users} {latestImports} 
          bind:importMumaUser bind:importLbUser {isImporting} {lbUsername} 
          onMessage={(m) => message = m} 
          onError={(e) => error = e} 
          onSelectUser={selectUser} 
          fetchLatestImports={fetchLatestImports} 
        />
      {:else if managementTabs.has($activeManagementTab)}
        <LazyView registry={managementTabs} name={$activeManagementTab} props={tabProps($activeManagementTab)} />
      {/if}
    {/if}
  {/if}
</div>
