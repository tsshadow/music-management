<script lang="ts">
  import { Search, Tag, Trash2 } from 'lucide-svelte';
  
  export let API_BASE: string;
  export let getHeaders: () => any;
  export let artistSearch: string;
  export let labelSearch: string;
  export let artists: any[];
  export let labels: any[];
  export let rules: any;
  export let artistGenreRules: any[];
  export let labelGenreRules: any[];
  export let fetchRules: () => Promise<void>;
  export let searchArtists: () => Promise<void>;
  export let searchLabels: () => Promise<void>;
  export let onMessage: (msg: string) => void;
  export let onError: (err: string) => void;

  let taggerSubTab = 'artists';
  let selectedArtistName = '';
  let selectedLabelName = '';
  let selectedGenreId: number | null = null;

  async function addArtistRule() {
    if (!selectedArtistName || !selectedGenreId) return;
    try {
      const res = await fetch(`${API_BASE}/api/rules/artist-genres`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          artist_name: selectedArtistName,
          genre_id: selectedGenreId
        })
      });
      if (res.ok) {
        onMessage(`Regel toegevoegd voor ${selectedArtistName}`);
        fetchRules();
      }
    } catch (err) {
      onError("Kon regel niet toevoegen.");
    }
  }

  async function addLabelRule() {
    if (!selectedLabelName || !selectedGenreId) return;
    try {
      const res = await fetch(`${API_BASE}/api/rules/label-genres`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          label_name: selectedLabelName,
          genre_id: selectedGenreId
        })
      });
      if (res.ok) {
        onMessage(`Regel toegevoegd voor ${selectedLabelName}`);
        fetchRules();
      }
    } catch (err) {
      onError("Kon regel niet toevoegen.");
    }
  }

  async function deleteArtistRule(id: number) {
    try {
      const res = await fetch(`${API_BASE}/api/rules/artist-genres/${id}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage("Regel verwijderd.");
        fetchRules();
      }
    } catch (err) {
      onError("Kon regel niet verwijderen.");
    }
  }

  async function deleteLabelRule(id: number) {
    try {
      const res = await fetch(`${API_BASE}/api/rules/label-genres/${id}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage("Regel verwijderd.");
        fetchRules();
      }
    } catch (err) {
      onError("Kon regel niet verwijderen.");
    }
  }

  async function triggerRescan() {
    if (!confirm("Weet je zeker dat je alle bestanden opnieuw wilt scannen? Dit kan even duren.")) return;
    try {
      const res = await fetch(`${API_BASE}/api/tagger/rescan`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage("Rescan voor alle bestanden getriggerd.");
      }
    } catch (err) {
      onError("Kon rescan niet triggeren.");
    }
  }
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex justify-between items-end">
    <div>
      <h1 class="text-6xl font-extrabold mb-4 tracking-tighter">Tagger Config</h1>
      <p class="text-spotify-lightgray text-lg">Beheer genres, artiesten en tag-regels voor je bibliotheek.</p>
    </div>
    <div class="pb-2">
      <button 
        on:click={triggerRescan}
        class="bg-white text-black text-xs font-bold px-4 py-2 rounded-full hover:bg-spotify-lightgray transition-colors"
      >
        FORCEER VOLLEDIGE RESCAN
      </button>
    </div>
  </header>

  <div class="flex gap-6 border-b border-white border-opacity-10">
    <button 
      on:click={() => taggerSubTab = 'artists'}
      class="pb-4 font-bold text-sm transition-colors relative {taggerSubTab === 'artists' ? 'text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      Artiesten & Labels
      {#if taggerSubTab === 'artists'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-spotify-green rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
    <button 
      on:click={() => taggerSubTab = 'genres'}
      class="pb-4 font-bold text-sm transition-colors relative {taggerSubTab === 'genres' ? 'text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      Genre Overzicht
      {#if taggerSubTab === 'genres'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-spotify-green rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
    <button 
      on:click={() => taggerSubTab = 'rules'}
      class="pb-4 font-bold text-sm transition-colors relative {taggerSubTab === 'rules' ? 'text-white' : 'text-spotify-lightgray hover:text-white'}"
    >
      Genre Koppelingen
      {#if taggerSubTab === 'rules'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-spotify-green rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
  </div>

  {#if taggerSubTab === 'artists'}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in fade-in duration-300">
      <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5 space-y-6">
        <h3 class="text-xl font-bold flex items-center gap-2"><Search size={20} class="text-spotify-green" /> Zoeken</h3>
        <div class="space-y-4">
          <div>
            <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-2">Artiest</label>
            <input 
              type="text" 
              bind:value={artistSearch} 
              on:input={searchArtists}
              placeholder="Naam..."
              class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 focus:outline-none focus:border-spotify-green"
            />
            <select 
              bind:value={selectedArtistName}
              class="w-full bg-spotify-dark border border-spotify-gray rounded-md mt-2 p-2 h-40 focus:outline-none focus:border-spotify-green"
              size="5"
            >
              {#each artists as artist}
                <option value={artist.name}>{artist.name}</option>
              {/each}
            </select>
          </div>
          <div>
            <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-2">Label</label>
            <input 
              type="text" 
              bind:value={labelSearch} 
              on:input={searchLabels}
              placeholder="Naam..."
              class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 focus:outline-none focus:border-spotify-green"
            />
            <select 
              bind:value={selectedLabelName}
              class="w-full bg-spotify-dark border border-spotify-gray rounded-md mt-2 p-2 h-40 focus:outline-none focus:border-spotify-green"
              size="5"
            >
              {#each labels as label}
                <option value={label.name}>{label.name}</option>
              {/each}
            </select>
          </div>
        </div>
      </div>

      <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5 space-y-6">
        <h3 class="text-xl font-bold flex items-center gap-2"><Tag size={20} class="text-spotify-green" /> Genre Toewijzen</h3>
        <div class="p-6 bg-black bg-opacity-20 rounded-xl space-y-6">
          <div>
            <label class="block text-xs font-bold text-spotify-lightgray uppercase mb-2">Kies Genre</label>
            <select 
              bind:value={selectedGenreId}
              class="w-full bg-spotify-dark border border-spotify-gray rounded-md p-3 focus:outline-none focus:border-spotify-green transition-colors"
            >
              <option value={null}>Selecteer...</option>
              {#each rules.genres as genre}
                <option value={genre.id}>{genre.name}</option>
              {/each}
            </select>
          </div>
          
          <div class="flex flex-col gap-3">
            <button 
              on:click={addArtistRule}
              disabled={!selectedArtistName || !selectedGenreId}
              class="w-full bg-spotify-green text-black font-extrabold py-4 rounded-full hover:scale-105 transition-transform disabled:opacity-50"
            >
              KOPPEL ARTIEST: {selectedArtistName || '...'}
            </button>
            <button 
              on:click={addLabelRule}
              disabled={!selectedLabelName || !selectedGenreId}
              class="w-full bg-white text-black font-extrabold py-4 rounded-full hover:scale-105 transition-transform disabled:opacity-50"
            >
              KOPPEL LABEL: {selectedLabelName || '...'}
            </button>
          </div>
        </div>
      </div>
    </div>

  {:else if taggerSubTab === 'genres'}
    <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden animate-in fade-in duration-300">
      <table class="w-full text-left">
        <thead class="bg-black bg-opacity-20 text-xs uppercase text-spotify-lightgray">
          <tr>
            <th class="p-4">Genre Name</th>
            <th class="p-4">Color</th>
            <th class="p-4">Rules</th>
            <th class="p-4">Status</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-spotify-gray divide-opacity-30">
          {#each rules.genres as genre}
            <tr class="hover:bg-white hover:bg-opacity-5 transition-colors">
              <td class="p-4 font-bold">{genre.name}</td>
              <td class="p-4">
                <div class="w-6 h-6 rounded-full border border-white border-opacity-10" style="background: {genre.color}"></div>
              </td>
              <td class="p-4 text-spotify-lightgray">
                {artistGenreRules.filter(r => r.genre_id === genre.id).length + labelGenreRules.filter(r => r.genre_id === genre.id).length} mappings
              </td>
              <td class="p-4">
                <span class="px-2 py-1 rounded text-[10px] font-bold uppercase bg-spotify-green text-black">Active</span>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

  {:else if taggerSubTab === 'rules'}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in fade-in duration-300">
      <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
        <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex items-center gap-2">Artiest Koppelingen</h3>
        <div class="max-h-[600px] overflow-y-auto">
          <table class="w-full text-left text-sm">
            <tbody class="divide-y divide-spotify-gray divide-opacity-30">
              {#each artistGenreRules as rule}
                <tr class="hover:bg-white hover:bg-opacity-5">
                  <td class="p-4 font-bold">{rule.artist_name}</td>
                  <td class="p-4">
                    <span class="px-2 py-1 bg-spotify-dark rounded text-spotify-green text-xs font-bold">{rule.genre_name}</span>
                  </td>
                  <td class="p-4 text-right">
                    <button on:click={() => deleteArtistRule(rule.id)} class="text-spotify-lightgray hover:text-red-500">
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>

      <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
        <h3 class="p-6 text-xl font-bold bg-black bg-opacity-20 flex items-center gap-2">Label Koppelingen</h3>
        <div class="max-h-[600px] overflow-y-auto">
          <table class="w-full text-left text-sm">
            <tbody class="divide-y divide-spotify-gray divide-opacity-30">
              {#each labelGenreRules as rule}
                <tr class="hover:bg-white hover:bg-opacity-5">
                  <td class="p-4 font-bold">{rule.label_name}</td>
                  <td class="p-4">
                    <span class="px-2 py-1 bg-spotify-dark rounded text-spotify-green text-xs font-bold">{rule.genre_name}</span>
                  </td>
                  <td class="p-4 text-right">
                    <button on:click={() => deleteLabelRule(rule.id)} class="text-spotify-lightgray hover:text-red-500">
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  {/if}
</section>
