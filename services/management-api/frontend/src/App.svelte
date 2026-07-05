<script lang="ts">
  import { onMount } from 'svelte';
  import { Home, Cloud, Scale, Database, Info, ExternalLink, Plus, RefreshCw, Music, Tag, Trash2, Search, Radio, Users, Key, Youtube, Activity, ShieldCheck, Terminal, Clock } from 'lucide-svelte';

  let activeTab = 'home';
  let config = { version: '...', phpmyadmin_url: '#' };
  let isLoggedIn = false;
  let username = '';
  let password = '';
  let loginError = '';
  let isLoggingIn = false;
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
  let containers = [];
  let systemLogs = '';
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
    avg_track_duration: 0
  };
  let selectedContainer = '';
  let selectedUser = null;
  let userLBAccount = null;
  let loading = true;
  let message = '';
  let error = '';

  // Form state
  let newAccountName = '';
  let newAccountId = '';
  
  // Scrobble Import State
  let importMumaUser = '';
  let importLbUser = '';
  let isImporting = false;
  
  // User Form State
  let newUsername = '';
  let newDisplayName = '';
  let userPassword = '';
  let lbUsername = '';
  let lbToken = '';
  
  // Editor state
  let artistSearch = '';
  let labelSearch = '';
  let selectedArtistName = '';
  let selectedLabelName = '';
  let selectedGenreId = null;
  let selectedServiceNotes = 'control-center';
  let apiKey = '';

  const API_BASE = import.meta.env.DEV ? 'http://localhost:8003' : '';

  onMount(() => {
    apiKey = localStorage.getItem('muma_api_key') || '';
    if (apiKey) {
      fetchData();
    } else {
      loading = false;
    }
  });

  async function handleLogin() {
    isLoggingIn = true;
    loginError = '';
    try {
      const res = await fetch(`${API_BASE}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password })
      });
      
      if (res.ok) {
        const data = await res.json();
        apiKey = data.api_key;
        localStorage.setItem('muma_api_key', apiKey);
        isLoggedIn = true;
        fetchData();
      } else {
        const data = await res.json();
        loginError = data.detail || 'Login mislukt';
      }
    } catch (err) {
      loginError = 'Kon niet verbinden met auth service';
    } finally {
      isLoggingIn = false;
    }
  }

  function logout() {
    apiKey = '';
    localStorage.removeItem('muma_api_key');
    isLoggedIn = false;
    activeTab = 'home';
  }

  function getHeaders(extra = {}) {
    const headers = { ...extra };
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
    }
    return headers;
  }

  function saveApiKey() {
    localStorage.setItem('muma_api_key', apiKey);
    message = "API Sleutel opgeslagen.";
    setTimeout(() => message = '', 2000);
    fetchData();
  }

  async function fetchStats() {
    try {
      const res = await fetch(`${API_BASE}/api/stats`, { headers: getHeaders() });
      if (res.ok) {
        stats = await res.json();
      }
    } catch (err) {
      console.error("Stats fetch error:", err);
    }
  }

  async function fetchData() {
    loading = true;
    error = '';
    try {
      const headers = getHeaders();
      const res = await fetch(`${API_BASE}/api/config`, { headers });
      if (res.status === 401 || res.status === 403) {
        isLoggedIn = false;
        loading = false;
        return;
      }
      
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
      
      // Load rules for editor
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

  async function fetchLatestImports() {
    try {
      const res = await fetch(`${API_BASE}/api/scrobble/import/latest`, { headers: getHeaders() });
      latestImports = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function startLbImport() {
    if (!importMumaUser) return;
    isImporting = true;
    try {
      const body = { username: importMumaUser };
      if (importLbUser) {
        body.lb_username = importLbUser;
      }

      const res = await fetch(`${API_BASE}/api/scrobble/import/listenbrainz`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify(body)
      });
      if (res.ok) {
        const data = await res.json();
        message = `ListenBrainz import gestart voor ${data.lb_username || 'gekoppeld account'}!`;
        fetchLatestImports();
        // Poll for updates every 3 seconds while active
        const interval = setInterval(async () => {
          await fetchLatestImports();
          const active = latestImports.some(i => i.status === 'running' || i.status === 'pending');
          if (!active) {
            clearInterval(interval);
            isImporting = false;
          }
        }, 3000);
      } else {
        error = "Kon import niet starten.";
      }
    } catch (err) {
      error = "Netwerkfout bij starten import.";
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

  async function addArtistRule() {
    if (!selectedArtistName || !selectedGenreId) return;
    try {
      const res = await fetch(`${API_BASE}/api/rules/artist-genres`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ artist_name: selectedArtistName, genre_id: selectedGenreId })
      });
      if (res.ok) {
        message = "Artiest regel toegevoegd";
        fetchRules();
        setTimeout(() => message = '', 2000);
      }
    } catch (err) {
      error = "Fout bij toevoegen regel";
    }
  }

  async function deleteArtistRule(id) {
    try {
      const res = await fetch(`${API_BASE}/api/rules/artist-genres/${id}`, { 
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        fetchRules();
      }
    } catch (err) {
      error = "Fout bij verwijderen regel";
    }
  }

  async function addLabelRule() {
    if (!selectedLabelName || !selectedGenreId) return;
    try {
      const res = await fetch(`${API_BASE}/api/rules/label-genres`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ label_name: selectedLabelName, genre_id: selectedGenreId })
      });
      if (res.ok) {
        message = "Label regel toegevoegd";
        fetchRules();
        setTimeout(() => message = '', 2000);
      }
    } catch (err) {
      error = "Fout bij toevoegen regel";
    }
  }

  async function deleteLabelRule(id) {
    try {
      const res = await fetch(`${API_BASE}/api/rules/label-genres/${id}`, { 
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        fetchRules();
      }
    } catch (err) {
      error = "Fout bij verwijderen regel";
    }
  }

  async function addAccount() {
    if (!newAccountName) return;
    try {
      const res = await fetch(`${API_BASE}/api/soundcloud`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ name: newAccountName, soundcloud_id: newAccountId || null })
      });
      const data = await res.json();
      if (res.ok) {
        message = data.message;
        newAccountName = '';
        newAccountId = '';
        fetchData();
        setTimeout(() => message = '', 3000);
      } else {
        error = data.detail || "Fout bij toevoegen account.";
        setTimeout(() => error = '', 5000);
      }
    } catch (err) {
      error = "Netwerkfout bij toevoegen account.";
    }
  }

  async function deleteSoundcloudAccount(name) {
    if (!confirm(`Weet je zeker dat je SoundCloud account ${name} wilt verwijderen?`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/soundcloud/${name}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        message = "SoundCloud account verwijderd";
        fetchData();
        setTimeout(() => message = '', 2000);
      }
    } catch (err) {
      error = "Fout bij verwijderen account";
    }
  }

  async function fetchYoutubeAccounts() {
    try {
      const res = await fetch(`${API_BASE}/api/youtube`, { headers: getHeaders() });
      youtubeAccounts = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function addYoutubeAccount() {
    if (!newAccountName) return;
    try {
      const res = await fetch(`${API_BASE}/api/youtube`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ name: newAccountName })
      });
      const data = await res.json();
      if (res.ok) {
        message = data.message;
        newAccountName = '';
        fetchYoutubeAccounts();
        setTimeout(() => message = '', 3000);
      } else {
        error = data.detail || "Fout bij toevoegen account.";
        setTimeout(() => error = '', 5000);
      }
    } catch (err) {
      error = "Netwerkfout bij toevoegen account.";
    }
  }

  async function deleteYoutubeAccount(name) {
    if (!confirm(`Weet je zeker dat je YouTube account ${name} wilt verwijderen?`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/youtube/${name}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        message = "YouTube account verwijderd";
        fetchYoutubeAccounts();
        setTimeout(() => message = '', 2000);
      }
    } catch (err) {
      error = "Fout bij verwijderen account";
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

  async function addUser() {
    if (!newUsername) return;
    try {
      const res = await fetch(`${API_BASE}/api/users`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ 
          username: newUsername, 
          display_name: newDisplayName || null,
          password: userPassword || null
        })
      });
      if (res.ok) {
        message = "Gebruiker toegevoegd (ook in LMS)";
        newUsername = '';
        newDisplayName = '';
        userPassword = '';
        fetchUsers();
        setTimeout(() => message = '', 2000);
      }
    } catch (err) {
      error = "Fout bij toevoegen gebruiker";
    }
  }

  async function deleteUser(user) {
    if (!confirm(`Weet je zeker dat je gebruiker ${user.username} wilt verwijderen? Dit verwijdert hem ook uit de LMS.`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${user.id}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        message = "Gebruiker verwijderd";
        if (selectedUser?.id === user.id) selectedUser = null;
        fetchUsers();
        setTimeout(() => message = '', 2000);
      }
    } catch (err) {
      error = "Fout bij verwijderen gebruiker";
    }
  }

  async function selectUser(user) {
    selectedUser = user;
    userLBAccount = null;
    userPassword = '';
    lbUsername = '';
    lbToken = '';
    
    try {
      const res = await fetch(`${API_BASE}/api/users/${user.id}/lb-account`, { headers: getHeaders() });
      if (res.ok) {
        userLBAccount = await res.json();
        if (userLBAccount) {
          lbUsername = userLBAccount.lb_username;
          lbToken = userLBAccount.lb_token;
        }
      }
    } catch (err) {
      console.error(err);
    }
  }

  async function updateLBAccount() {
    if (!selectedUser || !lbUsername || !lbToken) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/lb-account`, {
        method: 'PUT',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ lb_username: lbUsername, lb_token: lbToken })
      });
      if (res.ok) {
        message = "ListenBrainz account bijgewerkt";
        setTimeout(() => message = '', 2000);
      }
    } catch (err) {
      error = "Fout bij bijwerken LB account";
    }
  }

  async function updatePassword() {
    if (!selectedUser || !userPassword) return;
    try {
      const res = await fetch(`${API_BASE}/api/users/${selectedUser.id}/password`, {
        method: 'PUT',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ password: userPassword })
      });
      if (res.ok) {
        message = "Wachtwoord bijgewerkt (ook in LMS)";
        userPassword = '';
        setTimeout(() => message = '', 2000);
      } else {
        const data = await res.json();
        error = data.detail || "Fout bij bijwerken wachtwoord";
      }
    } catch (err) {
      error = "Netwerkfout bij bijwerken wachtwoord";
    }
  }

  async function syncLMSUsers() {
    try {
      const res = await fetch(`${API_BASE}/api/users/sync/lms`, { 
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        message = "LMS sync gestart...";
        setTimeout(() => {
          fetchUsers();
          message = "LMS sync voltooid (waarschijnlijk)";
          setTimeout(() => message = '', 2000);
        }, 2000);
      }
    } catch (err) {
      error = "Fout bij starten LMS sync";
    }
  }

  async function syncLMSDbUsers() {
    try {
      const res = await fetch(`${API_BASE}/api/users/sync/lms-db`, { 
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        message = "LMS DB sync gestart...";
        setTimeout(() => {
          fetchUsers();
          message = "LMS DB sync voltooid (waarschijnlijk)";
          setTimeout(() => message = '', 2000);
        }, 2000);
      }
    } catch (err) {
      error = "Fout bij starten LMS DB sync";
    }
  }

  async function fetchLogs(name) {
    selectedContainer = name;
    systemLogs = 'Laden...';
    try {
      const res = await fetch(`${API_BASE}/api/system/logs/${name}?tail=200`, { headers: getHeaders() });
      if (res.ok) {
        const data = await res.json();
        systemLogs = data.logs;
      } else {
        systemLogs = "Kon logs niet ophalen.";
      }
    } catch (err) {
      systemLogs = "Fout bij ophalen logs.";
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
      if (selectedContainer) {
        fetchLogs(selectedContainer);
      }
    } catch (err) {
      console.error(err);
    }
  }

</script>

{#if !isLoggedIn}
  <div class="h-screen w-screen bg-black flex flex-col items-center justify-center p-4 font-sans text-white">
    <div class="mb-8 flex flex-col items-center">
      <div class="w-20 h-20 bg-spotify-green rounded-full flex items-center justify-center mb-4 shadow-lg shadow-spotify-green/20">
        <Database size={40} class="text-black" />
      </div>
      <h1 class="text-white text-4xl font-black tracking-tighter italic">MuMa<span class="text-spotify-green not-italic">.</span></h1>
    </div>

    <div class="w-full max-w-sm bg-[#121212] p-10 rounded-xl shadow-2xl">
      <h2 class="text-white text-2xl font-bold mb-8 text-center">Beheerder Login</h2>
      
      {#if loginError}
        <div class="bg-red-500/10 border border-red-500/50 text-red-500 p-4 rounded-md mb-6 text-sm font-medium text-center">
          {loginError}
        </div>
      {/if}

      <form on:submit|preventDefault={handleLogin} class="space-y-5">
        <div>
          <label for="username" class="block text-xs font-bold text-white uppercase mb-2">Gebruikersnaam</label>
          <input 
            type="text" 
            id="username"
            bind:value={username}
            class="w-full bg-[#3e3e3e] border-0 rounded-md p-3 text-white placeholder-gray-400 focus:ring-2 focus:ring-white transition-all"
            placeholder="E-mailadres of gebruikersnaam"
            required
          />
        </div>
        
        <div>
          <label for="password" class="block text-xs font-bold text-white uppercase mb-2">Wachtwoord</label>
          <input 
            type="password" 
            id="password"
            bind:value={password}
            class="w-full bg-[#3e3e3e] border-0 rounded-md p-3 text-white placeholder-gray-400 focus:ring-2 focus:ring-white transition-all"
            placeholder="Wachtwoord"
            required
          />
        </div>

        <div class="pt-4">
          <button 
            type="submit" 
            disabled={isLoggingIn}
            class="w-full bg-spotify-green text-black font-black py-4 rounded-full hover:scale-105 active:scale-95 transition-all disabled:opacity-50 disabled:scale-100 uppercase tracking-widest text-sm"
          >
            {isLoggingIn ? 'Bezig...' : 'Log In'}
          </button>
        </div>
      </form>
    </div>
    
    <div class="mt-12 text-spotify-lightgray text-[10px] uppercase tracking-[0.2em] font-bold">
      MuMa Control Center &bull; 2026
    </div>
  </div>
{:else}
<div class="flex h-screen bg-spotify-dark overflow-hidden font-sans">
  <!-- Sidebar -->
  <aside class="w-64 bg-black flex flex-col flex-shrink-0">
    <div class="p-6">
      <h1 class="text-white text-xl font-bold flex items-center gap-2">
        <div class="w-8 h-8 bg-spotify-green rounded-full flex items-center justify-center">
          <Database size={18} class="text-black" />
        </div>
        MuMa Control
      </h1>
    </div>
    
    <nav class="flex-1 px-4 space-y-2">
      <button 
        on:click={() => activeTab = 'home'}
        class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold transition-colors {activeTab === 'home' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
      >
        <Home size={24} /> Home
      </button>
      <button 
        on:click={() => activeTab = 'soundcloud'}
        class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold transition-colors {activeTab === 'soundcloud' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
      >
        <Cloud size={24} /> SoundCloud
      </button>
      <button 
        on:click={() => activeTab = 'youtube'}
        class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold transition-colors {activeTab === 'youtube' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
      >
        <Youtube size={24} /> YouTube
      </button>
      <button 
        on:click={() => activeTab = 'users'}
        class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold transition-colors {activeTab === 'users' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
      >
        <Users size={24} /> Users
      </button>
      <button 
        on:click={() => activeTab = 'rules'}
        class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold transition-colors {activeTab === 'rules' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
      >
        <Scale size={24} /> Rules & Genres
      </button>
      <button 
        on:click={() => activeTab = 'editor'}
        class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold transition-colors {activeTab === 'editor' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
      >
        <Music size={24} /> Artist-Genre Editor
      </button>
      <button 
        on:click={() => activeTab = 'scrobble'}
        class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold transition-colors {activeTab === 'scrobble' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
      >
        <Radio size={24} /> Scrobble Service
      </button>
      <button 
        on:click={() => activeTab = 'versions'}
        class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold transition-colors {activeTab === 'versions' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
      >
        <Info size={24} /> System Versions
      </button>
      <button 
        on:click={() => { activeTab = 'health'; refreshSystemStatus(); }}
        class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold transition-colors {activeTab === 'health' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
      >
        <ShieldCheck size={24} /> Health & Activity
      </button>
      <button 
        on:click={() => { activeTab = 'stats'; fetchStats(); }}
        class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold transition-colors {activeTab === 'stats' ? 'bg-spotify-gray text-white' : 'text-spotify-lightgray hover:text-white'}"
      >
        <Activity size={24} /> Bibliotheek Stats
      </button>
      
      <div class="pt-4 mt-4 border-t border-spotify-gray">
        <a 
          href="https://spotify.teunschriks.nl"
          target="_blank"
          class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold text-spotify-lightgray hover:text-white transition-colors"
        >
          <ExternalLink size={24} /> MuMa Spotify
        </a>
        <a 
          href="https://spotify-alpha.teunschriks.nl"
          target="_blank"
          class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold text-spotify-lightgray hover:text-white transition-colors"
        >
          <ExternalLink size={24} /> MuMa Spotify-alpha
        </a>
        <a 
          href={config.phpmyadmin_url} 
          target="_blank"
          class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold text-spotify-lightgray hover:text-white transition-colors"
        >
          <ExternalLink size={24} /> phpMyAdmin
        </a>
        <button 
          on:click={logout}
          class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold text-red-500 hover:text-red-400 transition-colors mt-2"
        >
          <Key size={24} /> Uitloggen
        </button>
      </div>
    </nav>
    
    <div class="p-6 text-xs text-spotify-lightgray">
      <div class="flex items-center gap-2">
        <Info size={12} />
        Version {config.version}
      </div>
    </div>
  </aside>

  <!-- Main Content -->
  <main class="flex-1 overflow-y-auto bg-gradient-to-b from-spotify-gray to-spotify-black p-8">
    {#if message}
      <div class="bg-spotify-green text-black p-4 rounded-md mb-6 font-bold flex justify-between items-center">
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
        <section class="space-y-8 animate-in fade-in duration-500">
          <header class="flex flex-col md:flex-row md:items-end justify-between gap-4">
            <div>
              <h2 class="text-4xl font-extrabold mb-2">🚀 Release Notes</h2>
              <p class="text-spotify-lightgray">Updates en nieuwe features van het systeem.</p>
            </div>
            
            <div class="flex flex-col gap-2 min-w-[200px]">
              <label for="service-select" class="text-xs font-bold text-spotify-lightgray uppercase tracking-widest">Kies Service</label>
              <select 
                id="service-select"
                bind:value={selectedServiceNotes}
                class="bg-spotify-gray border border-white border-opacity-10 rounded-md p-2 text-white focus:outline-none focus:border-spotify-green"
              >
                {#each Object.keys(allNotes) as service}
                  <option value={service}>{service.charAt(0).toUpperCase() + service.slice(1).replace('-', ' ')}</option>
                {/each}
              </select>
            </div>
          </header>
          
          {#if allNotes[selectedServiceNotes]}
            <div class="bg-spotify-gray bg-opacity-40 p-8 rounded-xl backdrop-blur-sm border border-white border-opacity-5">
              <div class="md-content">
                {@html allNotes[selectedServiceNotes].release_notes}
              </div>
            </div>
            
            {#if allNotes[selectedServiceNotes].changelog && allNotes[selectedServiceNotes].changelog !== '<p>No changelog found.</p>'}
              <header class="pt-8">
                <h2 class="text-2xl font-bold mb-2 text-spotify-lightgray">📜 Technical Changelog</h2>
              </header>
              <div class="bg-spotify-dark p-8 rounded-xl border border-spotify-gray">
                <div class="md-content">
                  {@html allNotes[selectedServiceNotes].changelog}
                </div>
              </div>
            {/if}
          {:else}
            <div class="bg-spotify-gray bg-opacity-40 p-8 rounded-xl border border-white border-opacity-5 text-center text-spotify-lightgray">
              Geen gegevens beschikbaar voor deze service.
            </div>
          {/if}
        </section>

      {:else if activeTab === 'soundcloud'}
        <section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
          <header class="flex justify-between items-end">
            <div>
              <h2 class="text-4xl font-extrabold mb-2">☁️ SoundCloud Accounts</h2>
              <p class="text-spotify-lightgray">Beheer de accounts die worden gescand door de MuMa Downloader.</p>
            </div>
          </header>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <!-- Add Form -->
            <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
              <h3 class="text-xl font-bold mb-6 flex items-center gap-2">
                <Plus class="text-spotify-green" /> Account Toevoegen
              </h3>
              <form on:submit|preventDefault={addAccount} class="space-y-4">
                <div>
                  <label for="name" class="block text-sm font-bold text-spotify-lightgray mb-2">Account Slug</label>
                  <input 
                    type="text" 
                    id="name" 
                    bind:value={newAccountName}
                    placeholder="monstercat"
                    class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 focus:outline-none focus:border-spotify-green transition-colors"
                  />
                </div>
                <div>
                  <label for="id" class="block text-sm font-bold text-spotify-lightgray mb-2">SoundCloud ID (Optioneel)</label>
                  <input 
                    type="text" 
                    id="id" 
                    bind:value={newAccountId}
                    placeholder="123456"
                    class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 focus:outline-none focus:border-spotify-green transition-colors"
                  />
                </div>
                <button type="submit" class="w-full bg-spotify-green text-black font-extrabold py-3 rounded-full hover:scale-105 transition-transform">
                  TOEVOEGEN
                </button>
              </form>
            </div>

            <!-- List -->
            <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
              <table class="w-full text-left">
                <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray">
                  <tr>
                    <th class="p-4">Name / Slug</th>
                    <th class="p-4 text-right">ID</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-spotify-gray divide-opacity-30">
                  {#each accounts as account}
                    <tr class="hover:bg-white hover:bg-opacity-5 transition-colors group">
                      <td class="p-4">
                        <a href="https://soundcloud.com/{account.name}" target="_blank" class="font-bold flex items-center gap-2 group-hover:text-spotify-green">
                          {account.name} <ExternalLink size={14} class="opacity-0 group-hover:opacity-100 transition-opacity" />
                        </a>
                      </td>
                      <td class="p-4 text-right text-spotify-lightgray font-mono">
                        <div class="flex items-center justify-end gap-4">
                          {account.soundcloud_id || '-'}
                          <button on:click={() => deleteSoundcloudAccount(account.name)} class="text-spotify-lightgray hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </div>
        </section>

      {:else if activeTab === 'youtube'}
        <section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
          <header class="flex justify-between items-end">
            <div>
              <h2 class="text-4xl font-extrabold mb-2">📺 YouTube Accounts</h2>
              <p class="text-spotify-lightgray">Beheer de YouTube kanalen die worden gescand voor nieuwe muziek.</p>
            </div>
          </header>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <!-- Add Form -->
            <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
              <h3 class="text-xl font-bold mb-6 flex items-center gap-2">
                <Plus class="text-spotify-green" /> Kanaal Toevoegen
              </h3>
              <form on:submit|preventDefault={addYoutubeAccount} class="space-y-4">
                <div>
                  <label for="yt-name" class="block text-sm font-bold text-spotify-lightgray mb-2">Channel Handle / ID</label>
                  <input 
                    type="text" 
                    id="yt-name" 
                    bind:value={newAccountName}
                    placeholder="@Monstercat"
                    class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 focus:outline-none focus:border-spotify-green transition-colors"
                  />
                  <p class="text-xs text-spotify-lightgray mt-2">Gebruik de handle (bijv. @Monstercat) of de channel ID.</p>
                </div>
                <button type="submit" class="w-full bg-spotify-green text-black font-extrabold py-3 rounded-full hover:scale-105 transition-transform">
                  TOEVOEGEN
                </button>
              </form>
            </div>

            <!-- List -->
            <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
              <table class="w-full text-left">
                <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray">
                  <tr>
                    <th class="p-4">Channel</th>
                    <th class="p-4 text-right">Acties</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-spotify-gray divide-opacity-30">
                  {#each youtubeAccounts as account}
                    <tr class="hover:bg-white hover:bg-opacity-5 transition-colors group">
                      <td class="p-4">
                        <a href="https://www.youtube.com/{account.name.startsWith('@') ? account.name : 'channel/'+account.name}" target="_blank" class="font-bold flex items-center gap-2 group-hover:text-spotify-green">
                          {account.name} <ExternalLink size={14} class="opacity-0 group-hover:opacity-100 transition-opacity" />
                        </a>
                      </td>
                      <td class="p-4 text-right">
                        <button on:click={() => deleteYoutubeAccount(account.name)} class="text-spotify-lightgray hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity">
                          <Trash2 size={16} />
                        </button>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </div>
        </section>

      {:else if activeTab === 'rules'}
        <section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
          <header>
            <h2 class="text-4xl font-extrabold mb-2">⚖️ Rules & Genres</h2>
            <p class="text-spotify-lightgray">Database configuratie voor het importeren en taggen van muziek.</p>
          </header>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <!-- Genres -->
            <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
              <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20">Actieve Genres (rules_genres)</h3>
              <div class="max-h-[500px] overflow-y-auto">
                <table class="w-full text-left">
                  <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray sticky top-0">
                    <tr>
                      <th class="p-4 w-16">ID</th>
                      <th class="p-4">Genre</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-spotify-gray divide-opacity-30">
                    {#each rules.genres as genre}
                      <tr class="hover:bg-white hover:bg-opacity-5 transition-colors">
                        <td class="p-4 text-spotify-lightgray font-mono">{genre.id}</td>
                        <td class="p-4 font-bold">{genre.name}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Ignored -->
            <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
              <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20">Genegeerde Genres</h3>
              <div class="max-h-[500px] overflow-y-auto">
                <table class="w-full text-left">
                  <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray sticky top-0">
                    <tr>
                      <th class="p-4">Naam</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-spotify-gray divide-opacity-30">
                    {#each rules.ignored_genres as ignored}
                      <tr class="hover:bg-red-900 hover:bg-opacity-20 transition-colors">
                        <td class="p-4 text-red-200">{ignored.name}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>

      {:else if activeTab === 'editor'}
        <section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
          <header>
            <h2 class="text-4xl font-extrabold mb-2">🎨 Artist-Genre Editor</h2>
            <p class="text-spotify-lightgray">Koppel artiesten en labels aan specifieke genres.</p>
          </header>

          <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- Left: Selector -->
            <div class="lg:col-span-1 space-y-6">
              <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
                <h3 class="text-xl font-bold mb-4 flex items-center gap-2"><Music size={20} class="text-spotify-green" /> Artiest/Label Kiezen</h3>
                
                <div class="space-y-4">
                  <div class="flex flex-col gap-2">
                    <label class="text-xs font-bold text-spotify-lightgray uppercase">Zoek Artiest</label>
                    <div class="relative">
                      <Search class="absolute left-3 top-3 text-spotify-lightgray" size={16} />
                      <input 
                        type="text" 
                        bind:value={artistSearch} 
                        on:input={searchArtists}
                        placeholder="Naam..."
                        class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 pl-10 focus:outline-none focus:border-spotify-green"
                      />
                    </div>
                      <select 
                        bind:value={selectedArtistName}
                        class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 h-32 focus:outline-none focus:border-spotify-green transition-colors"
                        size="5"
                      >
                      {#each artists as artist}
                        <option value={artist.name}>{artist.name}</option>
                      {/each}
                    </select>
                  </div>

                  <div class="flex flex-col gap-2">
                    <label class="text-xs font-bold text-spotify-lightgray uppercase">Of Zoek Label</label>
                    <div class="relative">
                      <Search class="absolute left-3 top-3 text-spotify-lightgray" size={16} />
                      <input 
                        type="text" 
                        bind:value={labelSearch} 
                        on:input={searchLabels}
                        placeholder="Naam..."
                        class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 pl-10 focus:outline-none focus:border-spotify-green"
                      />
                    </div>
                    <select 
                      bind:value={selectedLabelName}
                      class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 h-32 focus:outline-none focus:border-spotify-green transition-colors"
                      size="5"
                    >
                      {#each labels as label}
                        <option value={label.name}>{label.name}</option>
                      {/each}
                    </select>
                  </div>
                </div>
              </div>

              <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
                <h3 class="text-xl font-bold mb-4 flex items-center gap-2"><Tag size={20} class="text-spotify-green" /> Genre Toewijzen</h3>
                <div class="space-y-4">
                  <select 
                    bind:value={selectedGenreId}
                    class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
                  >
                    <option value={null}>Kies een genre...</option>
                    {#each rules.genres as genre}
                      <option value={genre.id}>{genre.name}</option>
                    {/each}
                  </select>
                  
                  <div class="flex gap-2">
                    <button 
                      on:click={addArtistRule}
                      disabled={!selectedArtistName || !selectedGenreId}
                      class="flex-1 bg-spotify-green text-black font-bold py-3 rounded-full hover:scale-105 transition-transform disabled:opacity-50 disabled:hover:scale-100"
                    >
                      KOPPEL ARTIEST
                    </button>
                    <button 
                      on:click={addLabelRule}
                      disabled={!selectedLabelName || !selectedGenreId}
                      class="flex-1 bg-white text-black font-bold py-3 rounded-full hover:scale-105 transition-transform disabled:opacity-50 disabled:hover:scale-100"
                    >
                      KOPPEL LABEL
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- Right: Rules Lists -->
            <div class="lg:col-span-2 space-y-8">
              <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
                <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20">Artiest Genre Regels</h3>
                <div class="max-h-[400px] overflow-y-auto">
                  <table class="w-full text-left">
                    <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray sticky top-0">
                      <tr>
                        <th class="p-4">Artiest</th>
                        <th class="p-4">Genre</th>
                        <th class="p-4 w-16"></th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-spotify-gray divide-opacity-30">
                      {#each artistGenreRules as rule}
                        <tr class="hover:bg-white hover:bg-opacity-5 transition-colors">
                          <td class="p-4 font-bold">{rule.artist_name}</td>
                          <td class="p-4 text-spotify-green">{rule.genre_name}</td>
                          <td class="p-4 text-right">
                            <button on:click={() => deleteArtistRule(rule.id)} class="text-spotify-lightgray hover:text-red-500">
                              <Trash2 size={18} />
                            </button>
                          </td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              </div>

              <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
                <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20">Label Genre Regels</h3>
                <div class="max-h-[400px] overflow-y-auto">
                  <table class="w-full text-left">
                    <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray sticky top-0">
                      <tr>
                        <th class="p-4">Label</th>
                        <th class="p-4">Genre</th>
                        <th class="p-4 w-16"></th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-spotify-gray divide-opacity-30">
                      {#each labelGenreRules as rule}
                        <tr class="hover:bg-white hover:bg-opacity-5 transition-colors">
                          <td class="p-4 font-bold">{rule.label_name}</td>
                          <td class="p-4 text-spotify-green">{rule.genre_name}</td>
                          <td class="p-4 text-right">
                            <button on:click={() => deleteLabelRule(rule.id)} class="text-spotify-lightgray hover:text-red-500">
                              <Trash2 size={18} />
                            </button>
                          </td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        </section>
      {:else if activeTab === 'versions'}
        <section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
          <header>
            <h2 class="text-4xl font-extrabold mb-2">📟 System Versions</h2>
            <p class="text-spotify-lightgray">Centraal overzicht van alle draaiende service versies.</p>
          </header>

          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {#each Object.entries(versions) as [name, version]}
              <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5 flex flex-col gap-1">
                <span class="text-xs font-bold text-spotify-lightgray uppercase tracking-wider">{name}</span>
                <span class="text-xl font-mono {version === 'offline' ? 'text-red-500' : 'text-spotify-green'}">
                  {version}
                </span>
              </div>
            {/each}
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div class="bg-black bg-opacity-20 p-6 rounded-xl border border-spotify-gray border-dashed">
              <h3 class="font-bold mb-2 flex items-center gap-2 text-spotify-lightgray">
                <ExternalLink size={16} /> Externe Referenties
              </h3>
              <ul class="text-sm space-y-2 text-spotify-lightgray">
                <li>LMS: <span class="text-white">{versions.lms || 'Niet gedetecteerd'}</span></li>
                <li>Ultrasonic APK: <span class="text-white">{versions.ultrasonic || 'Niet gevonden'}</span></li>
              </ul>
            </div>

            <div class="bg-spotify-dark p-6 rounded-xl border border-spotify-gray space-y-4">
              <h3 class="text-xl font-bold flex items-center gap-2 text-white">
                <Key size={20} class="text-spotify-green" /> API Beveiliging
              </h3>
              <div class="space-y-4">
                <div>
                  <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-1">API Sleutel</label>
                  <input 
                    type="password" 
                    bind:value={apiKey}
                    placeholder="Voer sleutel in..."
                    class="w-full bg-spotify-gray bg-opacity-30 border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
                  />
                </div>
                <button 
                  on:click={saveApiKey}
                  class="w-full bg-spotify-green text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform"
                >
                  SLEUTEL OPSLAAN
                </button>
              </div>
            </div>
          </div>
        </section>
      {:else if activeTab === 'scrobble'}
        <section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
          <header>
            <h2 class="text-4xl font-extrabold mb-2">📻 Scrobble Service</h2>
            <p class="text-spotify-lightgray">Beheer luistergeschiedenis en ListenBrainz imports.</p>
          </header>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <!-- Import Form -->
            <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
              <h3 class="text-xl font-bold mb-6 flex items-center gap-2">
                <RefreshCw class="text-spotify-green {isImporting ? 'animate-spin' : ''}" /> ListenBrainz Import
              </h3>
              <form on:submit|preventDefault={startLbImport} class="space-y-4">
                <div>
                  <label for="muma-user" class="block text-sm font-bold text-spotify-lightgray mb-2">MuMa User</label>
                  <select 
                    id="muma-user" 
                    bind:value={importMumaUser}
                    on:change={(e) => {
                      const user = users.find(u => u.username === importMumaUser);
                      if (user) selectUser(user).then(() => {
                        importLbUser = lbUsername;
                      });
                    }}
                    class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 focus:outline-none focus:border-spotify-green transition-colors"
                  >
                    <option value="">Kies gebruiker...</option>
                    {#each users as user}
                      <option value={user.username}>{user.username}</option>
                    {/each}
                  </select>
                </div>
                <div>
                  <label for="lb-user" class="block text-sm font-bold text-spotify-lightgray mb-2">ListenBrainz Username</label>
                  <div class="relative">
                    <input 
                      type="text" 
                      id="lb-user" 
                      bind:value={importLbUser}
                      placeholder={lbUsername ? `Gekoppeld: ${lbUsername}` : "teunschriks"}
                      class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 focus:outline-none focus:border-spotify-green transition-colors"
                    />
                    {#if !importLbUser && lbUsername}
                      <span class="absolute right-3 top-3 text-xs text-spotify-green font-bold">GEKOPPELD</span>
                    {/if}
                  </div>
                  <p class="text-[10px] text-spotify-lightgray mt-1 italic">
                    Optioneel indien al gekoppeld in User Management.
                  </p>
                </div>
                <button 
                  type="submit" 
                  disabled={isImporting || !importMumaUser}
                  class="w-full bg-spotify-green text-black font-extrabold py-3 rounded-full hover:scale-105 transition-transform disabled:opacity-50 disabled:hover:scale-100"
                >
                  {isImporting ? 'IMPORT BEZIG...' : 'IMPORT STARTEN'}
                </button>
              </form>
            </div>

            <!-- Recent Imports -->
            <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
              <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex justify-between items-center">
                Recente Imports
                <button on:click={fetchLatestImports} class="text-spotify-lightgray hover:text-white transition-colors">
                  <RefreshCw size={16} />
                </button>
              </h3>
              <div class="overflow-x-auto">
                <table class="w-full text-left">
                  <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray">
                    <tr>
                      <th class="p-4">User</th>
                      <th class="p-4">Status</th>
                      <th class="p-4">Progress</th>
                      <th class="p-4 text-right">Started</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-spotify-gray divide-opacity-30 text-sm">
                    {#each latestImports as imp}
                      <tr class="hover:bg-white hover:bg-opacity-5 transition-colors">
                        <td class="p-4">
                          <div class="font-bold">{imp.username}</div>
                          <div class="text-xs text-spotify-lightgray">LB: {imp.lb_username}</div>
                        </td>
                        <td class="p-4">
                          <span class="px-2 py-1 rounded-full text-[10px] font-bold uppercase
                            {imp.status === 'completed' ? 'bg-spotify-green text-black' : 
                             imp.status === 'running' ? 'bg-blue-500 text-white' : 
                             imp.status === 'failed' ? 'bg-red-500 text-white' : 'bg-spotify-gray text-white'}">
                            {imp.status}
                          </span>
                        </td>
                        <td class="p-4">
                          <div class="w-full bg-spotify-dark rounded-full h-1.5 mb-1">
                            <div class="bg-spotify-green h-1.5 rounded-full" style="width: {imp.total_found > 0 ? (imp.processed / imp.total_found) * 100 : 0}%"></div>
                          </div>
                          <div class="text-[10px] text-spotify-lightgray">{imp.processed} / {imp.total_found}</div>
                        </td>
                        <td class="p-4 text-right text-xs text-spotify-lightgray">
                          {new Date(imp.started_at).toLocaleString()}
                        </td>
                      </tr>
                    {/each}
                    {#if latestImports.length === 0}
                      <tr>
                        <td colspan="4" class="p-8 text-center text-spotify-lightgray italic">Geen import geschiedenis gevonden.</td>
                      </tr>
                    {/if}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </section>
      {:else if activeTab === 'users'}
        <section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
          <header>
            <h2 class="text-4xl font-extrabold mb-2">👥 User Management</h2>
            <p class="text-spotify-lightgray">Beheer systeemgebruikers en hun externe account koppelingen.</p>
          </header>

          <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- User List -->
            <div class="lg:col-span-1 space-y-6">
              <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
                <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex justify-between items-center">
                  Gebruikers
                  <div class="flex gap-2">
                    <button 
                      on:click={syncLMSUsers} 
                      title="Sync van LMS"
                      class="text-spotify-lightgray hover:text-spotify-green transition-colors"
                    >
                      <RefreshCw size={16} />
                    </button>
                    <button 
                      on:click={fetchUsers} 
                      title="Verversen"
                      class="text-spotify-lightgray hover:text-white transition-colors"
                    >
                      <RefreshCw size={16} class="rotate-90" />
                    </button>
                  </div>
                </h3>
                <div class="max-h-[400px] overflow-y-auto">
                  <table class="w-full text-left text-sm">
                    <tbody class="divide-y divide-spotify-gray divide-opacity-30">
                      {#each users as user}
                        <tr 
                          class="hover:bg-white hover:bg-opacity-5 cursor-pointer transition-colors {selectedUser?.id === user.id ? 'bg-spotify-gray' : ''}"
                          on:click={() => selectUser(user)}
                        >
                          <td class="p-4">
                            <div class="flex justify-between items-center">
                              <div>
                                <div class="font-bold {selectedUser?.id === user.id ? 'text-spotify-green' : ''}">{user.username}</div>
                                <div class="text-xs text-spotify-lightgray">{user.display_name || ''}</div>
                              </div>
                              <button 
                                on:click|stopPropagation={() => deleteUser(user)}
                                class="text-spotify-lightgray hover:text-red-500 transition-colors p-2"
                                title="Verwijder gebruiker"
                              >
                                <Trash2 size={16} />
                              </button>
                            </div>
                          </td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Add User Form -->
              <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
                <h3 class="text-xl font-bold mb-4 flex items-center gap-2"><Plus size={20} class="text-spotify-green" /> Gebruiker Toevoegen</h3>
                <form on:submit|preventDefault={addUser} class="space-y-4">
                  <div>
                    <input 
                      type="text" 
                      bind:value={newUsername}
                      placeholder="Gebruikersnaam"
                      class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
                    />
                  </div>
                  <div>
                    <input 
                      type="text" 
                      bind:value={newDisplayName}
                      placeholder="Display Name (Optioneel)"
                      class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
                    />
                  </div>
                  <div>
                    <input 
                      type="password" 
                      bind:value={userPassword}
                      placeholder="Standaard Wachtwoord"
                      class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
                    />
                  </div>
                  <button type="submit" class="w-full bg-spotify-green text-black font-bold py-2 rounded-full hover:scale-105 transition-transform">
                    TOEVOEGEN
                  </button>
                </form>
              </div>
            </div>

            <!-- User Detail / External Accounts -->
            <div class="lg:col-span-2">
              {#if selectedUser}
                <div class="space-y-6 animate-in fade-in duration-300">
                  <div class="bg-spotify-gray p-8 rounded-xl border border-white border-opacity-5">
                    <div class="flex items-center gap-4 mb-8">
                      <div class="w-16 h-16 bg-spotify-green rounded-full flex items-center justify-center text-black text-2xl font-bold">
                        {selectedUser.username.charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <h3 class="text-3xl font-extrabold">{selectedUser.username}</h3>
                        <p class="text-spotify-lightgray">{selectedUser.display_name || 'Geen display name'}</p>
                      </div>
                    </div>

                    <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                      <!-- Password Section -->
                      <div class="space-y-4">
                        <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                          <Key size={20} class="text-spotify-green" /> Beveiliging
                        </h4>
                        <div class="bg-spotify-dark p-6 rounded-xl border border-spotify-gray space-y-4">
                          <div>
                            <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-1">Nieuw Wachtwoord</label>
                            <input 
                              type="password" 
                              bind:value={userPassword}
                              placeholder="••••••••"
                              class="w-full bg-spotify-gray bg-opacity-30 border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
                            />
                          </div>
                          <button 
                            on:click={updatePassword}
                            disabled={!userPassword}
                            class="w-full bg-spotify-green text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform disabled:opacity-50"
                          >
                            WACHTWOORD OPSLAAN
                          </button>
                        </div>
                      </div>

                      <!-- ListenBrainz Section -->
                      <div class="space-y-4">
                        <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                          <Radio size={20} class="text-[#EB743B]" /> ListenBrainz
                        </h4>
                  <div class="bg-spotify-dark p-6 rounded-xl border border-spotify-gray space-y-4">
                          <div>
                            <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-1">LB Username</label>
                            <input 
                              type="text" 
                              bind:value={lbUsername}
                              placeholder="ListenBrainz User"
                              class="w-full bg-spotify-gray bg-opacity-30 border border-spotify-gray rounded-md p-2 focus:outline-none focus:border-spotify-green transition-colors"
                            />
                          </div>
                          <div>
                            <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-1">API Token</label>
                            <div class="relative">
                              <Key class="absolute left-2 top-2.5 text-spotify-lightgray" size={16} />
                              <input 
                                type="password" 
                                bind:value={lbToken}
                                placeholder="Token"
                                class="w-full bg-spotify-gray bg-opacity-30 border border-spotify-gray rounded-md p-2 pl-9 focus:outline-none focus:border-spotify-green transition-colors font-mono text-sm"
                              />
                            </div>
                          </div>
                          <div class="flex gap-2">
                            <button 
                              on:click={() => {
                                activeTab = 'scrobble';
                                importMumaUser = selectedUser.username;
                                importLbUser = lbUsername;
                              }}
                              class="flex-1 bg-white text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform"
                            >
                              IMPORT STARTEN
                            </button>
                            <button 
                              on:click={updateLBAccount}
                              class="flex-1 bg-spotify-green text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform"
                            >
                              OPSLAAN
                            </button>
                          </div>
                        </div>
                      </div>

                      <!-- LMS Settings -->
                      <div class="space-y-4">
                        <h4 class="text-xl font-bold flex items-center gap-2 text-white">
                          <Database size={20} class="text-spotify-green" /> LMS Integratie
                        </h4>
                        <div class="bg-spotify-dark p-6 rounded-xl border border-spotify-gray space-y-4">
                          <p class="text-xs text-spotify-lightgray">Synchroniseer gebruikersgegevens direct vanuit Logitech Media Server.</p>
                          <div class="flex flex-col gap-2">
                            <button 
                              on:click={syncLMSUsers}
                              class="w-full bg-white text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform flex items-center justify-center gap-2"
                            >
                              <RefreshCw size={14} /> SYNC VIA API (SPELERS)
                            </button>
                            <button 
                              on:click={syncLMSDbUsers}
                              class="w-full bg-spotify-green text-black text-xs font-bold py-2 rounded-full hover:scale-105 transition-transform flex items-center justify-center gap-2"
                            >
                              <Database size={14} /> SYNC VIA DATABASE (USERS)
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              {:else}
                <div class="h-full flex items-center justify-center bg-spotify-gray bg-opacity-20 rounded-xl border border-dashed border-spotify-gray p-12 text-center text-spotify-lightgray">
                  <div>
                    <Users size={48} class="mx-auto mb-4 opacity-20" />
                    <p class="text-xl font-bold">Selecteer een gebruiker</p>
                    <p>Kies een gebruiker uit de lijst om instellingen te beheren.</p>
                  </div>
                </div>
              {/if}
            </div>
          </div>
        </section>
      {:else if activeTab === 'health'}
        <section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
          <header class="flex justify-between items-end">
            <div>
              <h2 class="text-4xl font-extrabold mb-2">🛡️ Health & Activity</h2>
              <p class="text-spotify-lightgray">Systeem monitoring en recente activiteit van alle workers.</p>
            </div>
            <button 
              on:click={refreshSystemStatus}
              class="bg-spotify-gray hover:bg-spotify-lightgray text-white px-4 py-2 rounded-full flex items-center gap-2 transition-colors"
            >
              <RefreshCw size={16} /> Vernieuwen
            </button>
          </header>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <!-- Container Status -->
            <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
              <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex items-center gap-2">
                <ShieldCheck class="text-spotify-green" /> Docker Containers
              </h3>
              <div class="max-h-[500px] overflow-y-auto">
                <table class="w-full text-left">
                  <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray sticky top-0">
                    <tr>
                      <th class="p-4">Name</th>
                      <th class="p-4">Status</th>
                      <th class="p-4 text-right">Logs</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-spotify-gray divide-opacity-30 text-sm">
                    {#each containers as container}
                      <tr class="hover:bg-white hover:bg-opacity-5 transition-colors">
                        <td class="p-4">
                          <div class="font-bold">{container.name}</div>
                          <div class="text-[10px] text-spotify-lightgray truncate max-w-[200px]">{container.image}</div>
                        </td>
                        <td class="p-4">
                          <span class="px-2 py-1 rounded-full text-[10px] font-bold uppercase
                            {container.status === 'running' ? 'bg-spotify-green text-black' : 'bg-red-500 text-white'}">
                            {container.status}
                          </span>
                        </td>
                        <td class="p-4 text-right">
                          <button 
                            on:click={() => fetchLogs(container.name)}
                            class="text-spotify-lightgray hover:text-spotify-green"
                          >
                            <Terminal size={18} />
                          </button>
                        </td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            </div>

            <!-- Recent Activity -->
            <div class="space-y-8">
              <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
                <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex items-center gap-2">
                  <Plus class="text-spotify-green" /> Recent Toegevoegd
                </h3>
                <div class="max-h-[250px] overflow-y-auto">
                  <ul class="divide-y divide-spotify-gray divide-opacity-30">
                    {#each activity.recent_added as item}
                      <li class="p-4 hover:bg-white hover:bg-opacity-5 flex justify-between items-center gap-4">
                        <div class="truncate">
                          <div class="font-bold text-sm truncate">{item.title || item.file_path.split('/').pop()}</div>
                          <div class="text-xs text-spotify-lightgray truncate">{item.artist || item.source}</div>
                        </div>
                        <div class="text-[10px] text-spotify-lightgray whitespace-nowrap text-right">
                          <Clock size={10} class="inline mb-0.5" /> {new Date(item.timestamp).toLocaleString()}
                        </div>
                      </li>
                    {/each}
                  </ul>
                </div>
              </div>

              <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
                <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex items-center gap-2">
                  <Tag class="text-spotify-green" /> Recent Getagged
                </h3>
                <div class="max-h-[250px] overflow-y-auto">
                  <ul class="divide-y divide-spotify-gray divide-opacity-30">
                    {#each activity.recent_tagged as item}
                      <li class="p-4 hover:bg-white hover:bg-opacity-5 flex justify-between items-center gap-4">
                        <div class="truncate">
                          <div class="font-bold text-sm truncate">{item.title || item.file_path.split('/').pop()}</div>
                          <div class="text-xs text-spotify-lightgray truncate">{item.artist || item.source}</div>
                        </div>
                        <div class="text-[10px] text-spotify-lightgray whitespace-nowrap text-right">
                          <Clock size={10} class="inline mb-0.5" /> {new Date(item.timestamp).toLocaleString()}
                        </div>
                      </li>
                    {/each}
                  </ul>
                </div>
              </div>
            </div>
          </div>

          <!-- Logs Viewer -->
          {#if selectedContainer}
            <div class="bg-black rounded-xl border border-spotify-gray overflow-hidden flex flex-col h-[500px] animate-in slide-in-from-bottom-4">
              <div class="bg-spotify-gray p-4 flex justify-between items-center border-b border-white border-opacity-10">
                <div class="flex items-center gap-2 font-bold text-sm">
                  <Terminal size={16} class="text-spotify-green" /> Logs: {selectedContainer}
                </div>
                <div class="flex gap-2">
                  <button on:click={() => fetchLogs(selectedContainer)} class="text-spotify-lightgray hover:text-white"><RefreshCw size={16} /></button>
                  <button on:click={() => selectedContainer = ''} class="text-spotify-lightgray hover:text-white text-xl leading-none">&times;</button>
                </div>
              </div>
              <pre class="p-4 text-xs font-mono text-spotify-lightgray overflow-auto flex-1 bg-black bg-opacity-50">
                {systemLogs}
              </pre>
            </div>
          {/if}
        </section>

      {:else if activeTab === 'stats'}
        <section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
          <header class="flex justify-between items-end">
            <div>
              <h2 class="text-4xl font-extrabold mb-2">📊 Bibliotheek Statistieken</h2>
              <p class="text-spotify-lightgray">Inzichten in je muziekcollectie en luistergedrag.</p>
            </div>
            <button on:click={fetchStats} class="bg-spotify-gray p-3 rounded-full hover:bg-white hover:bg-opacity-10 transition-colors">
              <RefreshCw size={20} />
            </button>
          </header>

          <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
              <div class="text-spotify-lightgray text-xs font-bold uppercase mb-1">Totaal Tracks</div>
              <div class="text-3xl font-extrabold text-spotify-green">{stats.total_tracks.toLocaleString()}</div>
            </div>
            <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
              <div class="text-spotify-lightgray text-xs font-bold uppercase mb-1">Totaal Artiesten</div>
              <div class="text-3xl font-extrabold text-white">{stats.total_artists.toLocaleString()}</div>
            </div>
            <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
              <div class="text-spotify-lightgray text-xs font-bold uppercase mb-1">Totaal Scrobbles</div>
              <div class="text-3xl font-extrabold text-blue-400">{stats.total_scrobbles.toLocaleString()}</div>
            </div>
            <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5">
              <div class="text-spotify-lightgray text-xs font-bold uppercase mb-1">Match Rate</div>
              <div class="text-3xl font-extrabold {stats.match_rate > 80 ? 'text-spotify-green' : 'text-yellow-500'}">{stats.match_rate}%</div>
            </div>
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <!-- Top Artists -->
            <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
              <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20">Top 10 Artiesten</h3>
              <table class="w-full text-left">
                <tbody class="divide-y divide-spotify-gray divide-opacity-30">
                  {#each stats.top_artists as artist, i}
                    <tr class="hover:bg-white hover:bg-opacity-5 transition-colors">
                      <td class="p-4 w-12 text-spotify-lightgray font-mono">{i + 1}.</td>
                      <td class="p-4 font-bold">{artist.name}</td>
                      <td class="p-4 text-right text-spotify-lightgray">{artist.track_count} tracks</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>

            <!-- Top Genres -->
            <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
              <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20">Populaire Genres</h3>
              <div class="p-6 space-y-4">
                {#each stats.top_genres as genre}
                  <div class="space-y-1">
                    <div class="flex justify-between text-sm font-bold">
                      <span>{genre.genre}</span>
                      <span class="text-spotify-lightgray">{genre.count}</span>
                    </div>
                    <div class="w-full bg-spotify-dark rounded-full h-2">
                      <div class="bg-spotify-green h-2 rounded-full" style="width: {stats.top_genres.length > 0 ? (genre.count / stats.top_genres[0].count) * 100 : 0}%"></div>
                    </div>
                  </div>
                {/each}
              </div>
            </div>
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <!-- Fun Stats -->
            <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5 space-y-4">
              <h3 class="text-xl font-bold">Leuke Weetjes</h3>
              <div class="space-y-4">
                <div class="flex justify-between items-center">
                  <span class="text-spotify-lightgray">Gem. Track Lengte</span>
                  <span class="font-bold">{Math.floor(stats.avg_track_duration / 60)}:{Math.floor(stats.avg_track_duration % 60).toString().padStart(2, '0')}</span>
                </div>
                <div class="flex justify-between items-center">
                  <span class="text-spotify-lightgray">Albums in collectie</span>
                  <span class="font-bold">{stats.total_albums || 'Onbekend'}</span>
                </div>
                <div class="flex justify-between items-center">
                  <span class="text-spotify-lightgray">Unmatched Scrobbles</span>
                  <span class="font-bold text-yellow-500">{stats.total_unmatched}</span>
                </div>
              </div>
            </div>

            <!-- Recently Added -->
            <div class="lg:col-span-2 bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
              <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20">Nieuw in Bibliotheek</h3>
              <table class="w-full text-left">
                <tbody class="divide-y divide-spotify-gray divide-opacity-30">
                  {#each stats.recently_added as track}
                    <tr class="hover:bg-white hover:bg-opacity-5 transition-colors">
                      <td class="p-4">
                        <div class="font-bold">{track.title}</div>
                        <div class="text-xs text-spotify-lightgray">{track.artist}</div>
                      </td>
                      <td class="p-4 text-right text-xs text-spotify-lightgray">
                        {new Date(track.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      {/if}
    {/if}
  </main>
</div>
{/if}

<style>
  /* Scrollbar styling */
  :global(::-webkit-scrollbar) {
    width: 12px;
  }
  :global(::-webkit-scrollbar-track) {
    background: transparent;
  }
  :global(::-webkit-scrollbar-thumb) {
    background: #5a5a5a;
    border-radius: 6px;
    border: 3px solid #121212;
  }
  :global(::-webkit-scrollbar-thumb:hover) {
    background: #888;
  }
</style>
