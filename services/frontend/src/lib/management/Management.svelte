<script>
  import { t } from '../i18n/index.js';
  import { onDestroy, onMount, untrack } from 'svelte';
  import { RefreshCw } from '@lucide/svelte';
  import { activeManagementTab, credentials, isAdmin, mumaApiKey, mumaApiUrl, userPermissions, mumaUser, hasPermission } from '../store.js';
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
  let rules = $state({ genres: [], ignored_genres: [] });
  let allNotes = $state({});
  let accounts = $state([]);
  let youtubeAccounts = $state([]);
  let artists = $state([]);
  let labels = $state([]);
  let artistGenreRules = $state([]);
  let labelGenreRules = $state([]);
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
  let artistSearch = $state('');
  let labelSearch = $state('');
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

  async function fetchData() {
    loading = true;
    const headers = getHeaders();
    try {
      // Fired a few at a time rather than all eleven at once: they all reach MuMa
      // through the LMS proxy, which refuses the eleventh with a 503 instead of
      // queueing it. See MAX_PARALLEL_MUMA_CALLS in lib/mumaApi.js.
      const [configBody, notesBody, rulesBody, accountsBody, youtubeBody, allNotesBody, importsBody, usersBody, containersBody, activityBody, statsBody] = await mapWithLimit(
        [
          '/api/config',
          '/api/notes',
          '/api/rules',
          '/api/soundcloud',
          '/api/youtube',
          '/api/all-notes',
          '/api/scrobble/import/latest',
          '/api/users',
          '/api/system/containers',
          '/api/system/activity',
          '/api/stats'
        ],
        (path) => fetchMumaJson(`${$mumaApiUrl}${path}`, { headers })
      );

      // The endpoint answers {config, groups}; the tabs below want the values map.
      // Reading the envelope as if it were flat is why the ntfy fields on the events
      // tab have always rendered empty.
      config = configBody?.config ?? configBody ?? {};
      notes = notesBody;
      rules = rulesBody;
      accounts = accountsBody;
      youtubeAccounts = youtubeBody;
      allNotes = allNotesBody;
      latestImports = importsBody;
      users = usersBody;
      containers = containersBody;
      activity = activityBody;
      stats = statsBody;

      fetchRules();
      searchArtists();
      searchLabels();
    } catch (err) {
      error = "Kon gegevens niet ophalen van de Management API.";
      console.error(err);
    } finally {
      loading = false;
    }
  }

  async function fetchRules() {
    try {
      const [artistRules, labelRules] = await Promise.all([
        fetchMumaJson(`${$mumaApiUrl}/api/rules/artist-genres`, { headers: getHeaders() }),
        fetchMumaJson(`${$mumaApiUrl}/api/rules/label-genres`, { headers: getHeaders() })
      ]);
      artistGenreRules = artistRules;
      labelGenreRules = labelRules;
    } catch (err) {
      console.error("Fout bij ophalen regels:", err);
    }
  }

  async function searchArtists() {
    try {
      artists = await fetchMumaJson(`${$mumaApiUrl}/api/artists?q=${artistSearch}`, { headers: getHeaders() });
    } catch (err) {
      console.error(err);
    }
  }

  async function searchLabels() {
    try {
      labels = await fetchMumaJson(`${$mumaApiUrl}/api/labels?q=${labelSearch}`, { headers: getHeaders() });
    } catch (err) {
      console.error(err);
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
        const res = await fetch(`${$mumaApiUrl}/api/artists/fetch-progress`, { headers: getHeaders() });
        fetchProgress = await res.json();
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
      const res = await fetch(`${$mumaApiUrl}/api/artists/images/stats`, { headers: getHeaders() });
      imageStats = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchStats() {
    try {
      const res = await fetch(`${$mumaApiUrl}/api/stats`, { headers: getHeaders() });
      stats = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchPlaylists() {
    if (!selectedUser) return;
    try {
      const res = await fetch(`${$mumaApiUrl}/api/users/${selectedUser.id}/dynamic-playlists`, { headers: getHeaders() });
      playlists = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchLatestImports() {
    try {
      const res = await fetch(`${$mumaApiUrl}/api/scrobble/import/latest`, { headers: getHeaders() });
      latestImports = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchUsers() {
    try {
      const res = await fetch(`${$mumaApiUrl}/api/users`, { headers: getHeaders() });
      users = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchRoles() {
    try {
      const res = await fetch(`${$mumaApiUrl}/api/roles`, { headers: getHeaders() });
      roles = await res.json();
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
              // The MuMa backend itself treats the shared system API key as an
              // always-allowed superuser (see rbac.has_permission/is_admin_auth),
              // which is what every Subsonic-authenticated admin actually
              // authenticates with (see AuthOverlay/store.js login flow). Mirror
              // that here so `hasPermission()` (gating individual user-management
              // actions below) doesn't stay stuck at "no permissions" just
              // because there's no specific `user` record for this key.
              userPermissions.set([]);
              mumaUser.set({ ...(currentUser || {}), is_admin: true });
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
          bind:artistSearch bind:labelSearch 
          {artists} {labels} {rules} {artistGenreRules} {labelGenreRules} 
          {fetchRules} {searchArtists} {searchLabels} 
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

<style>
  :global(.text-brand) {
    color: #1DB954;
  }
  :global(.bg-brand) {
    background-color: #1DB954;
  }
</style>
