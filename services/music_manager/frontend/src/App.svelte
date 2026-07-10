<script lang="ts">
  import { onMount } from 'svelte';
  import { RefreshCw } from 'lucide-svelte';

  // Import Tabs
  import OverviewTab from './lib/tabs/OverviewTab.svelte';
  import StatsTab from './lib/tabs/StatsTab.svelte';
  import ArtistImagesTab from './lib/tabs/ArtistImagesTab.svelte';
  import PlaylistsTab from './lib/tabs/PlaylistsTab.svelte';
  import TaggerTab from './lib/tabs/TaggerTab.svelte';
  import DownloadersTab from './lib/tabs/DownloadersTab.svelte';
  import ScrobbleTab from './lib/tabs/ScrobbleTab.svelte';
  import HealthTab from './lib/tabs/HealthTab.svelte';
  import UsersTab from './lib/tabs/UsersTab.svelte';
  import WorkerVersionsTab from './lib/tabs/WorkerVersionsTab.svelte';
  import NotificationsTab from './lib/tabs/NotificationsTab.svelte';
  import AboutTab from './lib/tabs/AboutTab.svelte';

  // Import Components
  import Sidebar from './lib/components/Sidebar.svelte';
  import Login from './lib/components/Login.svelte';

  // State
  let activeTab = 'home';
  let isLoggedIn = false;
  let apiKey = '';
  let loading = true;
  let message = '';
  let error = '';

  // Data State
  let config = { version: '...', phpmyadmin_url: '#' };
  let notes = { release_notes: '', changelog: '' };
  let rules = { genres: [], ignored_genres: [] };
  let versions = {};
  let allNotes = {};
  let accounts = [];
  let youtubeAccounts = [];
  let artists = [];
  let labels = [];
  let artistGenreRules = [];
  let labelGenreRules = [];
  let latestImports = [];
  let users = [];
  let playlists = [];
  let containers = [];
  let activity = { recent_added: [], recent_tagged: [] };
  let stats = {
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
  };

  // UI State
  let selectedUser = null;
  let currentUser = null;
  let lbUsername = '';
  let selectedServiceNotes = 'control-center';
  let artistSearch = '';
  let artistImageSearch = '';
  let labelSearch = '';
  let artistsWithImages = [];
  let allArtists = [];
  let fetchProgress = { active: false, total: 0, current: 0, last_artist: null, status: 'idle' };
  let imageStats = { total_artists: 0, artists_with_images: 0, artists_without_images: 0 };
  let importMumaUser = '';
  let importLbUser = '';
  let isImporting = false;

  const API_BASE = import.meta.env.DEV ? 'http://localhost:8003' : '';

  function getHeaders(extra = {}) {
    const headers: any = { ...extra };
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
    }
    return headers;
  }

  function logout() {
    apiKey = '';
    isLoggedIn = false;
    localStorage.removeItem('muma_api_key');
  }

  async function handleLoginSuccess(newApiKey: string) {
    apiKey = newApiKey;
    localStorage.setItem('muma_api_key', apiKey);
    await fetchData();
  }

  async function fetchData() {
    loading = true;
    const headers = getHeaders();
    try {
      isLoggedIn = true;
      const [configRes, notesRes, rulesRes, accountsRes, youtubeRes, versionsRes, allNotesRes, importsRes, usersRes, containersRes, activityRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/api/config`, { headers }),
        fetch(`${API_BASE}/api/notes`, { headers }),
        fetch(`${API_BASE}/api/rules`, { headers }),
        fetch(`${API_BASE}/api/soundcloud`, { headers }),
        fetch(`${API_BASE}/api/youtube`, { headers }),
        fetch(`${API_BASE}/api/versions`, { headers }),
        fetch(`${API_BASE}/api/all-notes`, { headers }),
        fetch(`${API_BASE}/api/scrobble/import/latest`, { headers }),
        fetch(`${API_BASE}/api/users`, { headers }),
        fetch(`${API_BASE}/api/system/containers`, { headers }),
        fetch(`${API_BASE}/api/system/activity`, { headers }),
        fetch(`${API_BASE}/api/stats`, { headers })
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
      
      // Load extra rules
      fetchRules();
      searchArtists();
      searchLabels();
    } catch (err) {
      error = "Kon gegevens niet ophalen van de API.";
      console.error(err);
    } finally {
      loading = false;
    }
  }

  async function fetchRules() {
    try {
      const [artistRulesRes, labelRulesRes] = await Promise.all([
        fetch(`${API_BASE}/api/rules/artist-genres`, { headers: getHeaders() }),
        fetch(`${API_BASE}/api/rules/label-genres`, { headers: getHeaders() })
      ]);
      artistGenreRules = await artistRulesRes.json();
      labelGenreRules = await labelRulesRes.json();
    } catch (err) {
      console.error("Fout bij ophalen regels:", err);
    }
  }

  async function searchArtists() {
    try {
      const res = await fetch(`${API_BASE}/api/artists?q=${artistSearch}`, { headers: getHeaders() });
      artists = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function searchLabels() {
    try {
      const res = await fetch(`${API_BASE}/api/labels?q=${labelSearch}`, { headers: getHeaders() });
      labels = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function searchArtistImages() {
    try {
      const res = await fetch(`${API_BASE}/api/artists/search?q=${artistImageSearch}`, { headers: getHeaders() });
      artistsWithImages = await res.json();
      
      // Also search all artists if needed
      if (artistImageSearch) {
        const resAll = await fetch(`${API_BASE}/api/artists/search-all?q=${artistImageSearch}`, { headers: getHeaders() });
        allArtists = await resAll.json();
      } else {
        allArtists = [];
      }
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchArtistImages() {
    message = "Achtergrondtaak voor afbeeldingen gestart...";
    try {
      const res = await fetch(`${API_BASE}/api/artists/fetch-images`, {
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

  async function manualFetchImage(artistId: number) {
    try {
      const res = await fetch(`${API_BASE}/api/artists/${artistId}/fetch-image`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        message = "Handmatige scan gestart...";
        setTimeout(searchArtistImages, 2000); // Refresh after a bit
      }
    } catch (err) {
      error = "Kon handmatige scan niet starten.";
    }
  }

  let progressInterval: any;
  function startProgressPolling() {
    if (progressInterval) clearInterval(progressInterval);
    progressInterval = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/artists/fetch-progress`, { headers: getHeaders() });
        fetchProgress = await res.json();
        if (!fetchProgress.active && fetchProgress.status !== 'running') {
          clearInterval(progressInterval);
          fetchImageStats();
          searchArtistImages();
        }
      } catch (err) {
        console.error("Error polling progress:", err);
      }
    }, 1000);
  }

  async function fetchImageStats() {
    try {
      const res = await fetch(`${API_BASE}/api/artists/images/stats`, { headers: getHeaders() });
      imageStats = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchStats() {
    try {
      const res = await fetch(`${API_BASE}/api/stats`, { headers: getHeaders() });
      stats = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchPlaylists() {
    if (!selectedUser) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/dynamic-playlists`, { headers: getHeaders() });
      playlists = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchLatestImports() {
    try {
      const res = await fetch(`${API_BASE}/api/scrobble/import/latest`, { headers: getHeaders() });
      latestImports = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function fetchUsers() {
    try {
      const res = await fetch(`${API_BASE}/api/users`, { headers: getHeaders() });
      users = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function selectUser(user) {
    selectedUser = user;
    if (user) {
      try {
        const res = await fetch(`${API_BASE}/api/users/${user.id}/listenbrainz`, {
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
        fetch(`${API_BASE}/api/system/containers`, { headers }),
        fetch(`${API_BASE}/api/system/activity`, { headers })
      ]);
      containers = await contRes.json();
      activity = await actRes.json();
    } catch (err) {
      console.error(err);
    }
  }

  onMount(async () => {
    apiKey = localStorage.getItem('muma_api_key') || '';
    if (apiKey) {
      try {
        const res = await fetch(`${API_BASE}/api/config`, { 
          headers: { 'X-API-Key': apiKey }
        });
        if (res.status === 401 || res.status === 403) {
          logout();
          loading = false;
          return;
        }
        
        const authRes = await fetch(`${API_BASE}/api/auth/verify`, {
          headers: { 'X-API-Key': apiKey }
        });
        if (authRes.ok) {
          const authData = await authRes.json();
          if (authData.type === 'user') {
            currentUser = authData.user;
            if (!selectedUser) selectedUser = currentUser;
          }
        }
        
        await fetchData();
        await fetchImageStats();
        startProgressPolling(); // Check if a task is already running
      } catch (e) {
        logout();
      }
    }
    loading = false;
  });

  // Navigation handlers
  function navigateToScrobbleImport(user: string, lbUser: string) {
    activeTab = 'scrobble';
    importMumaUser = user;
    importLbUser = lbUser;
  }
</script>

{#if !isLoggedIn}
  <Login {API_BASE} onLoginSuccess={handleLoginSuccess} />
{:else}
  <div class="flex h-screen bg-spotify-dark overflow-hidden font-sans text-white">
    <Sidebar 
      {activeTab} 
      onTabChange={(tab) => activeTab = tab}
      fetchStats={fetchStats}
      fetchPlaylists={fetchPlaylists}
      refreshSystemStatus={refreshSystemStatus}
      onMessage={(m) => message = m} 
      onError={(e) => error = e}
    />

    <main class="flex-1 overflow-y-auto bg-gradient-to-b from-spotify-gray to-spotify-dark p-8 relative">
      <!-- Top Bar / Logout -->
      <div class="absolute top-8 right-8 flex items-center gap-4 z-10">
        {#if currentUser}
          <div class="bg-black bg-opacity-40 px-4 py-2 rounded-full border border-white border-opacity-10 text-xs font-bold flex items-center gap-2">
             <div class="w-2 h-2 bg-spotify-green rounded-full"></div>
             {currentUser.username}
          </div>
        {/if}
        <button 
          on:click={logout}
          class="bg-black bg-opacity-40 hover:bg-opacity-60 text-white px-4 py-2 rounded-full border border-white border-opacity-10 text-xs font-bold transition-all"
        >
          LOGOUT
        </button>
      </div>

      <!-- Notifications -->
      {#if message}
        <div class="bg-spotify-green text-black p-4 rounded-md mb-6 font-bold flex justify-between items-center animate-in slide-in-from-top-4 duration-300">
          {message}
          <button on:click={() => message = ''}>&times;</button>
        </div>
      {/if}
      
      {#if error}
        <div class="bg-red-600 text-white p-4 rounded-md mb-6 font-bold flex justify-between items-center">
          {error}
          <button on:click={() => error = ''}>&times;</button>
        </div>
      {/if}

      {#if loading}
        <div class="flex items-center justify-center h-full">
          <RefreshCw class="animate-spin text-spotify-green" size={48} />
        </div>
      {:else}
        {#if activeTab === 'home'}
          <OverviewTab {containers} {activity} {config} {allNotes} {selectedServiceNotes} {notes} onNavigateToStats={() => activeTab = 'stats'} />
        {:else if activeTab === 'stats'}
          <StatsTab {stats} {fetchStats} {fetchArtistImages} />
        {:else if activeTab === 'images'}
          <ArtistImagesTab 
            {API_BASE} bind:artistImageSearch 
            {artistsWithImages} {allArtists} 
            {fetchArtistImages} {manualFetchImage}
            {fetchProgress} {imageStats}
            {searchArtistImages}
          />
        {:else if activeTab === 'playlists'}
          <PlaylistsTab 
            {API_BASE} {apiKey} {users} {playlists} {selectedUser} 
            getHeaders={getHeaders} {fetchPlaylists} 
            onSelectUser={selectUser} 
            onMessage={(m) => message = m} 
            onError={(e) => error = e} 
          />
        {:else if activeTab === 'tagger'}
          <TaggerTab 
            {API_BASE} getHeaders={getHeaders} 
            bind:artistSearch bind:labelSearch 
            {artists} {labels} {rules} {artistGenreRules} {labelGenreRules} 
            {fetchRules} {searchArtists} {searchLabels} 
            onMessage={(m) => message = m} 
            onError={(e) => error = e} 
          />
        {:else if activeTab === 'downloaders'}
          <DownloadersTab 
            {API_BASE} getHeaders={getHeaders} 
            {accounts} {youtubeAccounts} 
            onMessage={(m) => message = m} 
            onError={(e) => error = e} 
            refreshDownloaders={fetchData} 
          />
        {:else if activeTab === 'scrobble'}
          <ScrobbleTab 
            {API_BASE} getHeaders={getHeaders} 
            {users} {latestImports} 
            bind:importMumaUser bind:importLbUser {isImporting} {lbUsername} 
            onMessage={(m) => message = m} 
            onError={(e) => error = e} 
            onSelectUser={selectUser} 
            fetchLatestImports={fetchLatestImports} 
          />
        {:else if activeTab === 'health'}
          <HealthTab {containers} {activity} {API_BASE} getHeaders={getHeaders} {refreshSystemStatus} />
        {:else if activeTab === 'users'}
          <UsersTab 
            {users} {selectedUser} {API_BASE} getHeaders={getHeaders} {fetchUsers} 
            onMessage={(m) => message = m} 
            onError={(e) => error = e} 
            onSelectUser={selectUser} 
            navigateToScrobbleImport={navigateToScrobbleImport} 
          />
        {:else if activeTab === 'versions'}
          <WorkerVersionsTab {versions} />
        {:else if activeTab === 'about'}
          <AboutTab {API_BASE} {apiKey} />
        {:else if activeTab === 'notifications'}
          <NotificationsTab 
            {API_BASE} {getHeaders} 
            onMessage={(m) => message = m} 
            onError={(e) => error = e} 
            {config} 
          />
        {/if}
      {/if}
    </main>
  </div>
{/if}

<style>
  :global(:root) {
    --spotify-green: #1DB954;
    --spotify-dark: #121212;
    --spotify-gray: #282828;
    --spotify-lightgray: #b3b3b3;
  }

  :global(body) {
    background-color: var(--spotify-dark);
  }

  /* Custom scrollbar for sidebar */
  :global(.scrollbar-thin::-webkit-scrollbar) {
    width: 6px;
  }
  :global(.scrollbar-thin::-webkit-scrollbar-track) {
    background: transparent;
  }
  :global(.scrollbar-thin::-webkit-scrollbar-thumb) {
    background: rgba(255, 255, 255, 0.1);
    border-radius: 3px;
  }
  :global(.scrollbar-thin::-webkit-scrollbar-thumb:hover) {
    background: rgba(255, 255, 255, 0.2);
  }
</style>
