<script>
  import { t } from '../i18n/index.js';
  import { onDestroy, onMount, untrack } from 'svelte';
  import { RefreshCw } from '@lucide/svelte';
  import { activeManagementTab, credentials, isAdmin, mumaApiKey, mumaApiUrl, userPermissions, mumaUser, hasPermission } from '../store.js';

  // Import Tabs
  import OverviewTab from './tabs/OverviewTab.svelte';
  import AdvancedLibraryTab from './tabs/AdvancedLibraryTab.svelte';
  import ArtistImagesTab from './tabs/ArtistImagesTab.svelte';
  import PlaylistsTab from './tabs/PlaylistsTab.svelte';
  import TaggerTab from './tabs/TaggerTab.svelte';
  import GenreCurationTab from './tabs/GenreCurationTab.svelte';
  import DownloadersTab from './tabs/DownloadersTab.svelte';
  import ScrobbleTab from './tabs/ScrobbleTab.svelte';
  import HealthTab from './tabs/HealthTab.svelte';
  import ScannerTab from './tabs/ScannerTab.svelte';
  import LibrariesTab from './tabs/LibrariesTab.svelte';
  import UsersTab from './tabs/UsersTab.svelte';
  import UserRequestsTab from './tabs/UserRequestsTab.svelte';
  import WorkerVersionsTab from './tabs/WorkerVersionsTab.svelte';
  import NotificationsTab from './tabs/NotificationsTab.svelte';
  import AboutTab from './tabs/AboutTab.svelte';

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
  let versions = $state({});
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

  function getHeaders(extra = {}) {
    const headers = { ...extra };
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
    }
    return headers;
  }

  async function fetchData() {
    loading = true;
    const headers = getHeaders();
    try {
      const [configRes, notesRes, rulesRes, accountsRes, youtubeRes, versionsRes, allNotesRes, importsRes, usersRes, containersRes, activityRes, statsRes] = await Promise.all([
        fetch(`${$mumaApiUrl}/api/config`, { headers }),
        fetch(`${$mumaApiUrl}/api/notes`, { headers }),
        fetch(`${$mumaApiUrl}/api/rules`, { headers }),
        fetch(`${$mumaApiUrl}/api/soundcloud`, { headers }),
        fetch(`${$mumaApiUrl}/api/youtube`, { headers }),
        fetch(`${$mumaApiUrl}/api/versions`, { headers }),
        fetch(`${$mumaApiUrl}/api/all-notes`, { headers }),
        fetch(`${$mumaApiUrl}/api/scrobble/import/latest`, { headers }),
        fetch(`${$mumaApiUrl}/api/users`, { headers }),
        fetch(`${$mumaApiUrl}/api/system/containers`, { headers }),
        fetch(`${$mumaApiUrl}/api/system/activity`, { headers }),
        fetch(`${$mumaApiUrl}/api/stats`, { headers })
      ]);
      
      config = await configRes.json();
      notes = await notesRes.json();
      rules = await rulesRes.json();
      accounts = await accountsRes.json();
      youtubeAccounts = await youtubeRes.json();
      versions = await versionsRes.json();
      allNotes = await allNotesRes.json();
      latestImports = await importsRes.json();
      users = await usersRes.json();
      containers = await containersRes.json();
      activity = await activityRes.json();
      stats = await statsRes.json();
      
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
      const [artistRulesRes, labelRulesRes] = await Promise.all([
        fetch(`${$mumaApiUrl}/api/rules/artist-genres`, { headers: getHeaders() }),
        fetch(`${$mumaApiUrl}/api/rules/label-genres`, { headers: getHeaders() })
      ]);
      artistGenreRules = await artistRulesRes.json();
      labelGenreRules = await labelRulesRes.json();
    } catch (err) {
      console.error("Fout bij ophalen regels:", err);
    }
  }

  async function searchArtists() {
    try {
      const res = await fetch(`${$mumaApiUrl}/api/artists?q=${artistSearch}`, { headers: getHeaders() });
      artists = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function searchLabels() {
    try {
      const res = await fetch(`${$mumaApiUrl}/api/labels?q=${labelSearch}`, { headers: getHeaders() });
      labels = await res.json();
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
      const [contRes, actRes] = await Promise.all([
        fetch(`${$mumaApiUrl}/api/system/containers`, { headers }),
        fetch(`${$mumaApiUrl}/api/system/activity`, { headers })
      ]);
      containers = await contRes.json();
      activity = await actRes.json();
    } catch (err) {
      console.error(err);
    }
  }

  onMount(async () => {
    // 1. Try existing API key from store
    apiKey = $mumaApiKey || '';
    
    if (!apiKey && $credentials.username && $credentials.password) {
      // 2. Try auto-login with player credentials
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
            apiKey = loginData.api_key;
            mumaApiKey.set(apiKey);
          }
        }
      } catch (e) {
        console.error('Auto-login failed', e);
      }
    }

    if (apiKey) {
      try {
        const res = await fetch(`${$mumaApiUrl}/api/config`, { 
          headers: { 'X-API-Key': apiKey }
        });
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
      {:else if $activeManagementTab === 'versions'}
        <WorkerVersionsTab {versions} />
      {:else if $activeManagementTab === 'about'}
        <AboutTab {API_BASE} {apiKey} />
      {:else if $activeManagementTab === 'notifications'}
        <NotificationsTab 
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
