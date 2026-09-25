<script>
  import { t } from '../../i18n/index.js';
  import { Search, X } from '@lucide/svelte';
  import { apiGet } from './api.js';

  export let API_BASE;
  export let getHeaders;
  export let filters;
  export let genres = [];        // [{genre, state, count}]
  export let onChange;           // (filters) => void

  let artistQuery = '';
  let artistSuggestions = [];
  let artistTimer;

  $: whiteGenres = genres.filter((g) => g.state === 'white');
  $: unknownGenres = genres.filter((g) => g.state === 'unknown');

  function toggle(key, value) {
    const current = filters[key] || [];
    filters[key] = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    onChange(filters);
  }

  function setBound(key, event) {
    const raw = event.target.value;
    filters[key] = raw === '' ? null : Number(raw);
    onChange(filters);
  }

  function searchArtists() {
    clearTimeout(artistTimer);
    if (artistQuery.trim().length < 2) {
      artistSuggestions = [];
      return;
    }
    artistTimer = setTimeout(async () => {
      try {
        artistSuggestions = await apiGet(
          API_BASE, '/api/analytics/artist-search', {}, getHeaders,
          { q: artistQuery.trim(), limit: 15 });
      } catch (err) {
        artistSuggestions = [];
      }
    }, 250);
  }

  function addArtist(name) {
    if (!filters.artist.includes(name)) {
      filters.artist = [...filters.artist, name];
      onChange(filters);
    }
    artistQuery = '';
    artistSuggestions = [];
  }
</script>

<div class="w-full lg:w-64 shrink-0 bg-muma-spotify-panel border border-white/5 rounded-xl p-6 flex flex-col gap-8 lg:sticky lg:top-4">

  <div>
    <h3 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text mb-3">{$t('common.artist')}</h3>
    {#if filters.artist.length > 0}
      <div class="flex flex-wrap gap-1 mb-2">
        {#each filters.artist as name (name)}
          <button
            class="flex items-center gap-1 text-[11px] bg-brand/15 text-brand border border-brand/30 rounded-full px-2 py-0.5"
            on:click={() => toggle('artist', name)}
          >
            {name} <X size={11} />
          </button>
        {/each}
      </div>
    {/if}
    <div class="relative">
      <Search class="absolute left-2 top-1/2 -translate-y-1/2 text-muma-spotify-text" size={14} />
      <input
        type="text"
        bind:value={artistQuery}
        on:input={searchArtists}
        placeholder={$t('library.searchArtist')}
        class="w-full bg-muma-spotify-raised border-none rounded-md py-1.5 pl-7 pr-2 text-xs outline-none focus:ring-1 focus:ring-brand"
      />
      {#if artistSuggestions.length > 0}
        <div class="absolute z-10 mt-1 w-full bg-muma-spotify-raised border border-white/10 rounded-md max-h-48 overflow-y-auto">
          {#each artistSuggestions as suggestion (suggestion.artist)}
            <button
              class="w-full text-left px-2 py-1.5 text-xs hover:bg-white/10 flex justify-between gap-2"
              on:click={() => addArtist(suggestion.artist)}
            >
              <span class="truncate">{suggestion.artist}</span>
              <span class="text-muma-spotify-text shrink-0 tabular-nums">{suggestion.count}</span>
            </button>
          {/each}
        </div>
      {/if}
    </div>
  </div>

  <div>
    <h3 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text mb-3">{$t('nav.genres')}</h3>
    {#if genres.length === 0}
      <p class="text-[11px] text-muma-spotify-subtle italic">
        {$t('library.noGenresIndexed')}
      </p>
    {/if}
    <div class="flex flex-col gap-1 max-h-56 overflow-y-auto pr-2">
      {#each whiteGenres as g (g.genre)}
        <label class="flex items-center gap-2 cursor-pointer group py-0.5">
          <input type="checkbox" class="accent-brand rounded"
                 checked={filters.genre.includes(g.genre)}
                 on:change={() => toggle('genre', g.genre)} />
          <span class="text-xs text-muma-spotify-text group-hover:text-white truncate flex-1">{g.genre}</span>
          <span class="text-[10px] text-muma-spotify-subtle tabular-nums">{g.count}</span>
        </label>
      {/each}
    </div>

    {#if unknownGenres.length > 0}
      <h4 class="text-[10px] font-black uppercase tracking-widest text-yellow-600/80 mt-4 mb-2">
        {$t('library.toCurate', { count: unknownGenres.length })}
      </h4>
      <div class="flex flex-col gap-1 max-h-40 overflow-y-auto pr-2">
        {#each unknownGenres as g (g.genre)}
          <label class="flex items-center gap-2 cursor-pointer group py-0.5">
            <input type="checkbox" class="accent-brand rounded"
                   checked={filters.genre.includes(g.genre)}
                   on:change={() => toggle('genre', g.genre)} />
            <span class="text-xs text-[#8a8a8a] italic group-hover:text-white truncate flex-1">{g.genre}</span>
            <span class="text-[10px] text-muma-spotify-subtle tabular-nums">{g.count}</span>
          </label>
        {/each}
      </div>
    {/if}
  </div>

  <div>
    <h3 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text mb-3">BPM</h3>
    <div class="flex gap-2 items-center">
      <input type="number" min="0" max="400" placeholder={$t('library.min')} value={filters.bpm_min ?? ''}
             on:change={(e) => setBound('bpm_min', e)}
             class="w-full bg-muma-spotify-raised rounded-md py-1.5 px-2 text-xs outline-none focus:ring-1 focus:ring-brand" />
      <span class="text-muma-spotify-subtle text-xs">–</span>
      <input type="number" min="0" max="400" placeholder={$t('library.max')} value={filters.bpm_max ?? ''}
             on:change={(e) => setBound('bpm_max', e)}
             class="w-full bg-muma-spotify-raised rounded-md py-1.5 px-2 text-xs outline-none focus:ring-1 focus:ring-brand" />
    </div>
  </div>

  <div>
    <h3 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text mb-3">{$t('filter.year')}</h3>
    <div class="flex gap-2 items-center">
      <input type="number" min="1900" max="2100" placeholder={$t('library.from')} value={filters.year_min ?? ''}
             on:change={(e) => setBound('year_min', e)}
             class="w-full bg-muma-spotify-raised rounded-md py-1.5 px-2 text-xs outline-none focus:ring-1 focus:ring-brand" />
      <span class="text-muma-spotify-subtle text-xs">–</span>
      <input type="number" min="1900" max="2100" placeholder={$t('library.to')} value={filters.year_max ?? ''}
             on:change={(e) => setBound('year_max', e)}
             class="w-full bg-muma-spotify-raised rounded-md py-1.5 px-2 text-xs outline-none focus:ring-1 focus:ring-brand" />
    </div>
  </div>

  <label class="flex items-center gap-2 cursor-pointer group">
    <input type="checkbox" class="accent-brand rounded"
           checked={filters.analyzed === true}
           on:change={(e) => { filters.analyzed = e.target.checked ? true : null; onChange(filters); }} />
    <span class="text-xs text-muma-spotify-text group-hover:text-white">{$t('library.analysedOnly')}</span>
  </label>
</div>
