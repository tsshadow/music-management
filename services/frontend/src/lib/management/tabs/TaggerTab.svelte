<script >
  import { onMount } from 'svelte';
  import { t } from '../../i18n/index.js';
  import { Search, Tag, Trash2 } from '@lucide/svelte';

  export let API_BASE;
  export let getHeaders;
  export let artistSearch;
  export let labelSearch;
  export let artists;
  export let labels;
  export let rules;
  export let artistGenreRules;
  export let labelGenreRules;
  export let fetchRules;
  export let searchArtists;
  export let searchLabels;
  export let onMessage;
  export let onError;

  let taggerSubTab = 'artists';
  let selectedArtistName = '';
  let selectedLabelName = '';
  let selectedGenreId = null;

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
      onError($t('management.tagger.addRuleFailed'));
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
      onError($t('management.tagger.addRuleFailed'));
    }
  }

  async function deleteArtistRule(id) {
    try {
      const res = await fetch(`${API_BASE}/api/rules/artist-genres/${id}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.tagger.ruleDeleted'));
        fetchRules();
      }
    } catch (err) {
      onError($t('management.tagger.deleteRuleFailed'));
    }
  }

  async function deleteLabelRule(id) {
    try {
      const res = await fetch(`${API_BASE}/api/rules/label-genres/${id}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.tagger.ruleDeleted'));
        fetchRules();
      }
    } catch (err) {
      onError($t('management.tagger.deleteRuleFailed'));
    }
  }

  // What a rule change has queued up. Shown before the button is pressed, because a
  // wide match can touch more files than intended and the count is the only brake.
  let retagPending = { total: 0, by_reason: [] };

  async function fetchRetagPending() {
    try {
      const res = await fetch(`${API_BASE}/api/tagger/retag/pending`, { headers: getHeaders() });
      if (res.ok) retagPending = await res.json();
    } catch (err) {
      // Silent: the block simply stays hidden when the count cannot be fetched.
    }
  }

  onMount(fetchRetagPending);

  async function startRetag() {
    try {
      const res = await fetch(`${API_BASE}/api/tagger/retag/run`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.tagger.retagStarted'));
        retagPending = { total: 0, by_reason: [] };
      } else if (res.status === 409) {
        onError($t('management.tagger.retagBusy'));
      }
    } catch (err) {
      onError($t('management.tagger.retagFailed'));
    }
  }

  async function triggerRescan() {
    if (!confirm($t('management.tagger.confirmRescan'))) return;
    try {
      const res = await fetch(`${API_BASE}/api/tagger/rescan`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.tagger.rescanTriggered'));
      }
    } catch (err) {
      onError($t('management.tagger.rescanFailed'));
    }
  }
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex justify-between items-end">
    <div>
      <h1 class="text-6xl font-extrabold mb-4 tracking-tighter">{$t('management.tagger.title')}</h1>
      <p class="text-muma-spotify-text text-lg">{$t('management.tagger.subtitle')}</p>
    </div>
    <div class="pb-2">
      <button 
        on:click={triggerRescan}
        class="bg-white text-black text-xs font-bold px-4 py-2 rounded-full hover:bg-white/80 transition-colors"
      >
        {$t('management.tagger.forceRescan')}
      </button>
    </div>
  </header>

  {#if retagPending.total > 0}
    <div
      data-testid="retag-pending"
      class="bg-muma-spotify-panel p-4 rounded-xl border border-brand/40 flex items-center justify-between gap-4"
    >
      <p class="text-sm">
        <span class="font-bold">{retagPending.total}</span>
        {$t('management.tagger.retagPending')}
        <span class="text-muma-spotify-text">
          {retagPending.by_reason.map((r) => `${r.reason} (${r.count})`).join(', ')}
        </span>
      </p>
      <button
        on:click={startRetag}
        class="bg-brand text-black text-xs font-bold px-4 py-2 rounded-full hover:bg-white transition-colors whitespace-nowrap"
      >
        {$t('management.tagger.retagNow')}
      </button>
    </div>
  {/if}

  <div class="flex gap-6 border-b border-white/10">
    <button 
      on:click={() => taggerSubTab = 'artists'}
      class="pb-4 font-bold text-sm transition-colors relative {taggerSubTab === 'artists' ? 'text-white' : 'text-muma-spotify-text hover:text-white'}"
    >
      Artiesten & Labels
      {#if taggerSubTab === 'artists'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-brand rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
    <button 
      on:click={() => taggerSubTab = 'genres'}
      class="pb-4 font-bold text-sm transition-colors relative {taggerSubTab === 'genres' ? 'text-white' : 'text-muma-spotify-text hover:text-white'}"
    >
      Genre Overzicht
      {#if taggerSubTab === 'genres'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-brand rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
    <button 
      on:click={() => taggerSubTab = 'rules'}
      class="pb-4 font-bold text-sm transition-colors relative {taggerSubTab === 'rules' ? 'text-white' : 'text-muma-spotify-text hover:text-white'}"
    >
      Genre Koppelingen
      {#if taggerSubTab === 'rules'}
        <div class="absolute bottom-0 left-0 right-0 h-1 bg-brand rounded-full animate-in fade-in duration-300"></div>
      {/if}
    </button>
  </div>

  {#if taggerSubTab === 'artists'}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in fade-in duration-300">
      <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5 space-y-6">
        <h3 class="text-xl font-bold flex items-center gap-2"><Search size={20} class="text-brand" /> {$t('management.tagger.search')}</h3>
        <div class="space-y-4">
          <div>
            <label for="artistSearchInput" class="block text-xs font-bold text-muma-spotify-text uppercase mb-2">{$t('common.artist')}</label>
            <input 
              id="artistSearchInput"
              type="text" 
              bind:value={artistSearch} 
              on:input={searchArtists}
              placeholder={$t('management.tagger.namePlaceholder')}
              class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-3 focus:outline-none focus:border-brand"
            />
            <select 
              bind:value={selectedArtistName}
              class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md mt-2 p-2 h-40 focus:outline-none focus:border-brand"
              size="5"
            >
              {#each artists as artist (artist.name)}
                <option value={artist.name}>{artist.name}</option>
              {/each}
            </select>
          </div>
          <div>
            <label for="labelSearchInput" class="block text-xs font-bold text-muma-spotify-text uppercase mb-2">{$t('library.label')}</label>
            <input 
              id="labelSearchInput"
              type="text" 
              bind:value={labelSearch} 
              on:input={searchLabels}
              placeholder={$t('management.tagger.namePlaceholder')}
              class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-3 focus:outline-none focus:border-brand"
            />
            <select 
              bind:value={selectedLabelName}
              class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md mt-2 p-2 h-40 focus:outline-none focus:border-brand"
              size="5"
            >
              {#each labels as label (label.name)}
                <option value={label.name}>{label.name}</option>
              {/each}
            </select>
          </div>
        </div>
      </div>

      <div class="bg-muma-spotify-panel p-6 rounded-xl border border-white/5 space-y-6">
        <h3 class="text-xl font-bold flex items-center gap-2"><Tag size={20} class="text-brand" /> {$t('management.tagger.assignGenre')}</h3>
        <div class="p-6 bg-black/20 rounded-xl space-y-6">
          <div>
            <label for="genreSelect" class="block text-xs font-bold text-muma-spotify-text uppercase mb-2">{$t('management.tagger.pickGenre')}</label>
            <select 
              id="genreSelect"
              bind:value={selectedGenreId}
              class="w-full bg-muma-spotify-dark border border-muma-spotify-panel rounded-md p-3 focus:outline-none focus:border-brand transition-colors"
            >
              <option value={null}>{$t('management.tagger.select')}</option>
              {#each rules.genres as genre (genre.id)}
                <option value={genre.id}>{genre.name}</option>
              {/each}
            </select>
          </div>
          
          <div class="flex flex-col gap-3">
            <button 
              on:click={addArtistRule}
              disabled={!selectedArtistName || !selectedGenreId}
              class="w-full bg-brand text-black font-extrabold py-4 rounded-full hover:scale-105 transition-transform disabled:opacity-50"
            >
              {$t('management.tagger.linkArtist', { name: selectedArtistName || '...' })}
            </button>
            <button 
              on:click={addLabelRule}
              disabled={!selectedLabelName || !selectedGenreId}
              class="w-full bg-white text-black font-extrabold py-4 rounded-full hover:scale-105 transition-transform disabled:opacity-50"
            >
              {$t('management.tagger.linkLabel', { name: selectedLabelName || '...' })}
            </button>
          </div>
        </div>
      </div>
    </div>

  {:else if taggerSubTab === 'genres'}
    <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden animate-in fade-in duration-300">
      <table class="w-full text-left">
        <thead class="bg-black/20 text-xs uppercase text-muma-spotify-text">
          <tr>
            <th class="p-4">{$t('management.tagger.genreName')}</th>
            <th class="p-4">{$t('management.tagger.color')}</th>
            <th class="p-4">{$t('management.tagger.rules')}</th>
            <th class="p-4">{$t('management.health.status')}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-muma-spotify-panel/30">
          {#each rules.genres as genre (genre.id)}
            <tr class="hover:bg-white/5 transition-colors">
              <td class="p-4 font-bold">{genre.name}</td>
              <td class="p-4">
                <div class="w-6 h-6 rounded-full border border-white/10" style="background: {genre.color}"></div>
              </td>
              <td class="p-4 text-muma-spotify-text">
                {artistGenreRules.filter(r => r.genre_id === genre.id).length + labelGenreRules.filter(r => r.genre_id === genre.id).length} mappings
              </td>
              <td class="p-4">
                <span class="px-2 py-1 rounded text-[10px] font-bold uppercase bg-brand text-black">{$t('management.tagger.active')}</span>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>

  {:else if taggerSubTab === 'rules'}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-8 animate-in fade-in duration-300">
      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
        <h3 class="p-6 text-xl font-bold bg-black/20 flex items-center gap-2">{$t('management.tagger.artistLinks')}</h3>
        <div class="max-h-[600px] overflow-y-auto">
          <table class="w-full text-left text-sm">
            <tbody class="divide-y divide-muma-spotify-panel/30">
              {#each artistGenreRules as rule (rule.id)}
                <tr class="hover:bg-white/5">
                  <td class="p-4 font-bold">{rule.artist_name}</td>
                  <td class="p-4">
                    <span class="px-2 py-1 bg-muma-spotify-dark rounded text-brand text-xs font-bold">{rule.genre_name}</span>
                  </td>
                  <td class="p-4 text-right">
                    <button on:click={() => deleteArtistRule(rule.id)} class="text-muma-spotify-text hover:text-red-500">
                      <Trash2 size={16} />
                    </button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      </div>

      <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
        <h3 class="p-6 text-xl font-bold bg-black/20 flex items-center gap-2">{$t('management.tagger.labelLinks')}</h3>
        <div class="max-h-[600px] overflow-y-auto">
          <table class="w-full text-left text-sm">
            <tbody class="divide-y divide-muma-spotify-panel/30">
              {#each labelGenreRules as rule (rule.id)}
                <tr class="hover:bg-white/5">
                  <td class="p-4 font-bold">{rule.label_name}</td>
                  <td class="p-4">
                    <span class="px-2 py-1 bg-muma-spotify-dark rounded text-brand text-xs font-bold">{rule.genre_name}</span>
                  </td>
                  <td class="p-4 text-right">
                    <button on:click={() => deleteLabelRule(rule.id)} class="text-muma-spotify-text hover:text-red-500">
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
