<script lang="ts">
  import { onMount } from 'svelte';
  import { Home, Cloud, Scale, Database, Info, ExternalLink, Plus, RefreshCw } from 'lucide-svelte';

  let activeTab = 'home';
  let config = { version: '...', phpmyadmin_url: '#' };
  let notes = { release_notes: '', changelog: '' };
  let rules = { genres: [], ignored_genres: [] };
  let accounts = [];
  let loading = true;
  let message = '';
  let error = '';

  // Form state
  let newAccountName = '';
  let newAccountId = '';

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
    } catch (err) {
      error = "Kon gegevens niet ophalen van de API.";
      console.error(err);
    } finally {
      loading = false;
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
              <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20">Actieve Genres (rules_genres_new)</h3>
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
