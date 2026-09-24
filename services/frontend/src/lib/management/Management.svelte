<script>
  import { t } from '../i18n/index.js';
  import { onDestroy, onMount, untrack } from 'svelte';
  import { RefreshCw } from '@lucide/svelte';
  import { activeManagementTab, credentials, isAdmin, mumaApiKey, mumaApiUrl, userPermissions, mumaUser, hasPermission, endLeftoverSharedKeySession } from '../store.js';
  import { getHeaders as sharedHeaders, fetchMumaJson, mapWithLimit } from '../mumaApi.js';
  import { MANAGEMENT_TABS } from '../router.js';

  // Import Tabs
  import OverviewTab from './tabs/OverviewTab.svelte';
  import AdvancedLibraryTab from './tabs/AdvancedLibraryTab.svelte';
  import ArtistImagesTab from './tabs/ArtistImagesTab.svelte';
  import PlaylistsTab from './tabs/PlaylistsTab.svelte';
  import TaggerTab from './tabs/TaggerTab.svelte';
  import GenreCurationTab from './tabs/GenreCurationTab.svelte';
  import ArtistCurationTab from './tabs/ArtistCurationTab.svelte';
  import LabelsTab from './tabs/LabelsTab.svelte';
  import FestivalsTab from './tabs/FestivalsTab.svelte';
  import LineupsTab from './tabs/LineupsTab.svelte';
  import LabelProposalsTab from './tabs/LabelProposalsTab.svelte';
  import PodcastCurationTab from './tabs/PodcastCurationTab.svelte';
  import RadioTab from './tabs/RadioTab.svelte';
  import NewsTab from './tabs/NewsTab.svelte';
  import DownloadersTab from './tabs/DownloadersTab.svelte';
  import ScrobbleTab from './tabs/ScrobbleTab.svelte';
  import HealthTab from './tabs/HealthTab.svelte';
  import ScannerTab from './tabs/ScannerTab.svelte';
  import LibrariesTab from './tabs/LibrariesTab.svelte';
  import UsersTab from './tabs/UsersTab.svelte';
  import UserRequestsTab from './tabs/UserRequestsTab.svelte';
  import EventsTab from './tabs/EventsTab.svelte';
  import ConfigTab from './tabs/ConfigTab.svelte';

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
      if (bodies.every((body) => body === FAILED)) error = "Kon gegevens niet ophalen van de Management API.";
    } catch (err) {
      error = "Kon gegevens niet ophalen van de Management API.";
      console.error(err);
    } finally {
      loading = false;
    }
  }

  async function fetchArtistImages() {
    message = "Achtergrondtaak voor afbeeldingen gestart...";
    try {
      const res = await fetch(`${$mumaApiUrl}/api/artists/fetch-images`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        message = "Afbeeldingen fetch taak succesvol gestart!";
        startProgressPolling();
      }
    } catch (err) {
      error = "Kon fetch taak niet starten.";
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

  /**
   * Exchanges the player's Subsonic credentials for a MuMa API key.
   *
   * @returns {Promise<string>} The new key, or '' when there are no
   *   credentials to log in with or the login was refused.
   */
  async function loginWithPlayerCredentials() {
    if (!$credentials.username || !$credentials.password) return '';
    try {
      const loginRes = await fetch(`${$mumaApiUrl}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: $credentials.username,
          password: $credentials.password
        })
      });

      if (loginRes.ok) {
        const loginData = await loginRes.json();
        if (loginData.api_key) {
          mumaApiKey.set(loginData.api_key);
          return loginData.api_key;
        }
      }
    } catch (e) {
      console.error('Auto-login failed', e);
    }
    return '';
  }

  onMount(async () => {
    // 1. Try existing API key from store
    apiKey = $mumaApiKey || '';

    // 2. Try auto-login with player credentials
    if (!apiKey) {
      apiKey = await loginWithPlayerCredentials();
    }

    if (apiKey) {
      try {
        let res = await fetch(`${$mumaApiUrl}/api/config`, { 
          headers: { 'X-API-Key': apiKey }
        });
        // 3. A persisted key the backend no longer accepts (a rotated or
        // no-longer-resolving system key, an account whose key was reissued)
        // used to wedge this screen forever: step 2 only ran when there was no
        // key at all, so every visit rendered "kan niet verbinden" until the
        // user cleared localStorage by hand. Drop it and log in once more.
        if (!res.ok && (res.status === 401 || res.status === 403)) {
          mumaApiKey.set('');
          const freshKey = await loginWithPlayerCredentials();
          if (freshKey && freshKey !== apiKey) {
            apiKey = freshKey;
            res = await fetch(`${$mumaApiUrl}/api/config`, {
              headers: { 'X-API-Key': apiKey }
            });
          }
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
      } catch (e) {
        isLoggedIn = false;
      }
    } else {
      isLoggedIn = false;
    }
    loading = false;
  });

  function navigateToScrobbleImport(user, lbUser) {
    activeManagementTab.set('scrobble');
    importMumaUser = user;
    importLbUser = lbUser;
  }
</script>

<div class="flex flex-col gap-8 w-full h-full min-h-0 overflow-y-auto">
  {#if $isAdmin === false && !hasPermission('users.read')}
    <div class="flex items-center justify-center h-full">
      <div class="bg-[#181818] p-8 rounded-xl border border-white/5 max-w-md w-full text-center">
        <h2 class="text-2xl font-bold mb-4">{$t('management.noAccess')}</h2>
        <p class="text-[#b3b3b3] mb-6">{$t('management.noAccessHelp')}</p>
      </div>
    </div>
  {:else if !isLoggedIn}
    <div class="flex items-center justify-center h-full">
      <div class="bg-[#181818] p-8 rounded-xl border border-white/5 max-w-md w-full text-center">
        <h2 class="text-2xl font-bold mb-4">{$t('management.connecting')}</h2>
        <p class="text-[#b3b3b3] mb-6">{$t('management.connectFailed')}</p>
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
      {#if $activeManagementTab === 'overview'}
        <OverviewTab {containers} {activity} {config} {allNotes} {selectedServiceNotes} {notes} {stats} {fetchStats} {fetchArtistImages} />
      {:else if $activeManagementTab === 'library'}
        <AdvancedLibraryTab {API_BASE} {getHeaders} onMessage={(m) => message = m} onError={(e) => error = e} />
      {:else if $activeManagementTab === 'libraries'}
        <LibrariesTab onMessage={(m) => message = m} onError={(e) => error = e} />
      {:else if $activeManagementTab === 'scanner'}
        <ScannerTab onMessage={(m) => message = m} onError={(e) => error = e} />
      {:else if $activeManagementTab === 'images'}
        <ArtistImagesTab
          {API_BASE} {apiKey} getHeaders={getHeaders}
          {fetchArtistImages} {fetchProgress} {imageStats}
          refreshStats={fetchImageStats}
          onMessage={(m) => message = m}
          onError={(e) => error = e}
        />
      {:else if $activeManagementTab === 'playlists'}
        <PlaylistsTab 
          {API_BASE} {apiKey} {users} {playlists} {selectedUser} 
          getHeaders={getHeaders} {fetchPlaylists} 
          onSelectUser={selectUser} 
          onMessage={(m) => message = m} 
          onError={(e) => error = e} 
        />
      {:else if $activeManagementTab === 'tagger'}
        <TaggerTab
          {API_BASE} getHeaders={getHeaders}
          onMessage={(m) => message = m}
          onError={(e) => error = e}
        />
      {:else if $activeManagementTab === 'genre-curation'}
        <GenreCurationTab
          {API_BASE} getHeaders={getHeaders}
          onMessage={(m) => message = m}
          onError={(e) => error = e}
        />
      {:else if $activeManagementTab === 'artist-curation'}
        <ArtistCurationTab
          {API_BASE} getHeaders={getHeaders}
          onMessage={(m) => message = m}
          onError={(e) => error = e}
        />
      {:else if $activeManagementTab === 'labels'}
        <LabelsTab
          {API_BASE} getHeaders={getHeaders}
          onMessage={(m) => message = m}
          onError={(e) => error = e}
        />
      {:else if $activeManagementTab === 'festivals'}
        <FestivalsTab
          {API_BASE} getHeaders={getHeaders}
          onMessage={(m) => message = m}
          onError={(e) => error = e}
        />
      {:else if $activeManagementTab === 'lineups'}
        <LineupsTab
          {API_BASE} getHeaders={getHeaders}
          onMessage={(m) => message = m}
          onError={(e) => error = e}
        />
      {:else if $activeManagementTab === 'label-proposals'}
        <LabelProposalsTab
          {API_BASE} getHeaders={getHeaders}
          onMessage={(m) => message = m}
          onError={(e) => error = e}
        />
      {:else if $activeManagementTab === 'podcast-curation'}
        <PodcastCurationTab
          {API_BASE} getHeaders={getHeaders}
          onMessage={(m) => message = m}
          onError={(e) => error = e}
        />
      {:else if $activeManagementTab === 'radio'}
        <RadioTab
          {API_BASE} getHeaders={getHeaders}
          onMessage={(m) => message = m}
          onError={(e) => error = e}
        />
      {:else if $activeManagementTab === 'news'}
        <NewsTab
          {API_BASE} getHeaders={getHeaders}
          onMessage={(m) => message = m}
          onError={(e) => error = e}
        />
      {:else if $activeManagementTab === 'downloaders'}
        <DownloadersTab 
          {API_BASE} getHeaders={getHeaders} 
          {accounts} {youtubeAccounts} 
          onMessage={(m) => message = m} 
          onError={(e) => error = e} 
          refreshDownloaders={fetchData} 
        />
      {:else if $activeManagementTab === 'scrobble'}
        <ScrobbleTab 
          {API_BASE} getHeaders={getHeaders} 
          {users} {latestImports} 
          bind:importMumaUser bind:importLbUser {isImporting} {lbUsername} 
          onMessage={(m) => message = m} 
          onError={(e) => error = e} 
          onSelectUser={selectUser} 
          fetchLatestImports={fetchLatestImports} 
        />
      {:else if $activeManagementTab === 'health'}
        <HealthTab {containers} {activity} {API_BASE} getHeaders={getHeaders} {refreshSystemStatus} />
      {:else if $activeManagementTab === 'users'}
        <UsersTab 
          {users} {roles} {selectedUser} {API_BASE} getHeaders={getHeaders} {fetchUsers} 
          onMessage={(m) => message = m} 
          onError={(e) => error = e} 
          onSelectUser={selectUser} 
          navigateToScrobbleImport={navigateToScrobbleImport} 
        />
      {:else if $activeManagementTab === 'user-requests'}
        <UserRequestsTab 
          {API_BASE} getHeaders={getHeaders} {users}
          onMessage={(m) => message = m} 
          onError={(e) => error = e} 
        />
      {:else if $activeManagementTab === 'config'}
        <ConfigTab
          {API_BASE} {getHeaders}
          onMessage={(m) => message = m}
          onError={(e) => error = e}
        />
      {:else if $activeManagementTab === 'events'}
        <EventsTab
          {API_BASE} {getHeaders}
          onMessage={(m) => message = m}
          onError={(e) => error = e}
          {config}
        />
      {/if}
    {/if}
  {/if}
</div>
