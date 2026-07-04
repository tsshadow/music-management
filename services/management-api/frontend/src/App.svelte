<script lang="ts">
  import { onMount } from 'svelte';
  import { Home, Cloud, Scale, Database, Info, ExternalLink, Plus, RefreshCw, Music, Tag, Trash2, Search } from 'lucide-svelte';

  let activeTab = 'home';
  let config = { version: '...', phpmyadmin_url: '#' };
  let notes = { release_notes: '', changelog: '' };
  let rules = { genres: [], ignored_genres: [] };
  let accounts = [];
  let artists = [];
  let labels = [];
  let artistGenreRules = [];
  let labelGenreRules = [];
  let loading = true;
  let message = '';
  let error = '';

  // Form state
  let newAccountName = '';
  let newAccountId = '';
  
  // Editor state
  let artistSearch = '';
  let labelSearch = '';
  let selectedArtistName = '';
  let selectedLabelName = '';
  let selectedGenreId = null;

  const API_BASE = import.meta.env.DEV ? 'http://localhost:8003' : '';

  async function fetchData() {
    loading = true;
    try {
      const [configRes, notesRes, rulesRes, accountsRes] = await Promise.all([
        fetch(`${API_BASE}/api/config`),
        fetch(`${API_BASE}/api/notes`),
        fetch(`${API_BASE}/api/rules`),
        fetch(`${API_BASE}/api/soundcloud`)
      ]);
      
      config = await configRes.json();
      notes = await notesRes.json();
      rules = await rulesRes.json();
      accounts = await accountsRes.json();
      
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

  async function fetchRules() {
    try {
      const [artistRulesRes, labelRulesRes] = await Promise.all([
        fetch(`${API_BASE}/api/rules/artist-genres`),
        fetch(`${API_BASE}/api/rules/label-genres`)
      ]);
      artistGenreRules = await artistRulesRes.json();
      labelGenreRules = await labelRulesRes.json();
    } catch (err) {
      console.error("Fout bij ophalen regels:", err);
    }
  }

  async function searchArtists() {
    try {
      const res = await fetch(`${API_BASE}/api/artists?q=${encodeURIComponent(artistSearch)}`);
      artists = await res.json();
    } catch (err) {
      console.error(err);
    }
  }

  async function searchLabels() {
    try {
      const res = await fetch(`${API_BASE}/api/labels?q=${encodeURIComponent(labelSearch)}`);
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
        headers: { 'Content-Type': 'application/json' },
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
      const res = await fetch(`${API_BASE}/api/rules/artist-genres/${id}`, { method: 'DELETE' });
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
        headers: { 'Content-Type': 'application/json' },
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
      const res = await fetch(`${API_BASE}/api/rules/label-genres/${id}`, { method: 'DELETE' });
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
        headers: { 'Content-Type': 'application/json' },
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

  onMount(fetchData);
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
          <header>
            <h2 class="text-4xl font-extrabold mb-2">🚀 Release Notes</h2>
            <p class="text-spotify-lightgray">Updates en nieuwe features van het systeem.</p>
          </header>
          
          <div class="bg-spotify-gray bg-opacity-40 p-8 rounded-xl backdrop-blur-sm border border-white border-opacity-5">
            <div class="md-content">
              {@html notes.release_notes}
            </div>
          </div>
          
          <header class="pt-8">
            <h2 class="text-2xl font-bold mb-2 text-spotify-lightgray">📜 Technical Changelog</h2>
          </header>
          <div class="bg-spotify-dark p-8 rounded-xl border border-spotify-gray">
            <div class="md-content">
              {@html notes.changelog}
            </div>
          </div>
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
                      class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 h-32"
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
                      class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2 h-32"
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
                    class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-2"
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
