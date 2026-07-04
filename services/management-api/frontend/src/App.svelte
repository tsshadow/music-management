<script lang="ts">
  import { onMount } from 'svelte';
  import { Home, Cloud, Scale, Database, Info, ExternalLink, Plus, RefreshCw, Music, Tag, Trash2, Search, Radio, Users, Key } from 'lucide-svelte';

  let activeTab = 'home';
  let config = { version: '...', phpmyadmin_url: '#' };
  let notes = { release_notes: '', changelog: '' };
  let rules = { genres: [], ignored_genres: [] };
  let versions = {};
  let allNotes = {};
  let accounts = [];
  let artists = [];
  let labels = [];
  let artistGenreRules = [];
  let labelGenreRules = [];
  let latestImports = [];
  let users = [];
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
    fetchData();
  });

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

  async function fetchData() {
    loading = true;
    try {
      const headers = getHeaders();
      const [configRes, notesRes, rulesRes, accountsRes, versionsRes, allNotesRes, importsRes, usersRes] = await Promise.all([
        fetch(`${API_BASE}/api/config`, { headers }),
        fetch(`${API_BASE}/api/notes`, { headers }),
        fetch(`${API_BASE}/api/rules`, { headers }),
        fetch(`${API_BASE}/api/soundcloud`, { headers }),
        fetch(`${API_BASE}/api/versions`, { headers }),
        fetch(`${API_BASE}/api/all-notes`, { headers }),
        fetch(`${API_BASE}/api/scrobble/import/latest`, { headers }),
        fetch(`${API_BASE}/api/users`, { headers })
      ]);
      
      config = await configRes.json();
      notes = await notesRes.json();
      rules = await rulesRes.json();
      accounts = await accountsRes.json();
      versions = await versionsRes.json();
      allNotes = await allNotesRes.json();
      latestImports = await importsRes.json();
      users = await usersRes.json();
      
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
      // If we have a selected user and an LB account, use that lbUsername if importLbUser is empty
      let lbUserToUse = importLbUser;
      if (!lbUserToUse && selectedUser && lbUsername) {
        lbUserToUse = lbUsername;
      }
      
      if (!lbUserToUse) {
        error = "ListenBrainz gebruikersnaam is vereist.";
        isImporting = false;
        return;
      }

      const res = await fetch(`${API_BASE}/api/scrobble/import/listenbrainz`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ username: importMumaUser, lb_username: lbUserToUse })
      });
      if (res.ok) {
        message = "ListenBrainz import gestart!";
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
        body: JSON.stringify({ username: newUsername, display_name: newDisplayName || null })
      });
      if (res.ok) {
        message = "Gebruiker toegevoegd";
        newUsername = '';
        newDisplayName = '';
        fetchUsers();
      }
    } catch (err) {
      error = "Fout bij toevoegen gebruiker";
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
        headers: { 'Content-Type': 'application/json' },
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

</script>

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
      
      <div class="pt-4 mt-4 border-t border-spotify-gray">
        <a 
          href={config.phpmyadmin_url} 
          target="_blank"
          class="w-full flex items-center gap-4 px-4 py-3 rounded-md font-bold text-spotify-lightgray hover:text-white transition-colors"
        >
          <ExternalLink size={24} /> phpMyAdmin
        </a>
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
                      <td class="p-4 text-right text-spotify-lightgray font-mono">{account.soundcloud_id || '-'}</td>
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
                  <input 
                    type="text" 
                    id="lb-user" 
                    bind:value={importLbUser}
                    placeholder="teunschriks"
                    class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 focus:outline-none focus:border-spotify-green transition-colors"
                  />
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
                            <div class="font-bold {selectedUser?.id === user.id ? 'text-spotify-green' : ''}">{user.username}</div>
                            <div class="text-xs text-spotify-lightgray">{user.display_name || ''}</div>
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
      {/if}
    {/if}
  </main>
</div>

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
