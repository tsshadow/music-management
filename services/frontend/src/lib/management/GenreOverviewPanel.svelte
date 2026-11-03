<script>
  /**
   * Every approved genre, most tracks first, with what the tagger knows about it:
   * hardness, the genres it rolls up into, and how many artist and label rules
   * point at it. The row is the way into the genre's edit page (hierarchy,
   * hardness); whether a genre exists at all is the queue's question, next door.
   *
   * This replaces the "Genre Overzicht" that lived on the tagger page and listed
   * every row of the rules table, rejected and queued ones included.
   */
  import { format, t } from '../i18n/index.js';
  import { onMount } from 'svelte';
  import { RefreshCw, Search, Pencil } from '@lucide/svelte';
  import { activeView } from '../store.js';
  import { filterOverview } from './genreRules.js';

  let { API_BASE, getHeaders, onError, refreshKey = 0 } = $props();

  let rows = $state([]);
  let total = $state(0);
  let loading = $state(false);
  let search = $state('');

  const visibleRows = $derived(filterOverview(rows, search));
  const n = (value) => $format.number(value);

  async function fetchRows() {
    loading = true;
    try {
      const res = await fetch(`${API_BASE}/api/curation/genres?limit=1000`, { headers: getHeaders() });
      if (res.ok) {
        const body = await res.json();
        rows = body.rows || [];
        total = body.total || 0;
      } else {
        onError($t('management.genres.overviewLoadFailed'));
      }
    } catch {
      onError($t('management.genres.overviewLoadNetworkError'));
    } finally {
      loading = false;
    }
  }

  /** The edit page is a view of the player, not a management tab: leave Management for it. */
  function edit(row) {
    activeView.set(`genre-edit:${row.name}`);
  }

  onMount(fetchRows);
  // A rule added or removed on a sibling panel changes the counts here.
  $effect(() => {
    if (refreshKey) fetchRows();
  });
</script>

<div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden" data-testid="genre-overview">
  <div class="p-6 bg-black/20 flex justify-between items-center gap-4 flex-wrap">
    <h3 class="text-xl font-bold flex items-center gap-2">
      {$t('management.genres.overview')}
      <span class="text-muma-spotify-text text-sm font-normal">({n(visibleRows.length)}{search ? ` / ${n(total)}` : ''})</span>
    </h3>
    <div class="flex items-center gap-3">
      <div class="relative">
        <Search size={16} class="absolute left-3 top-1/2 -translate-y-1/2 text-muma-spotify-text" />
        <input
          type="text"
          bind:value={search}
          placeholder={$t('management.genres.searchPlaceholder')}
          aria-label={$t('management.genres.overviewSearchLabel')}
          class="bg-muma-spotify-dark border border-muma-spotify-panel rounded-full pl-9 pr-4 py-2 text-sm focus:outline-none focus:border-brand transition-colors"
        />
      </div>
      <button
        type="button"
        onclick={fetchRows}
        disabled={loading}
        aria-label={$t('common.refresh')}
        class="text-muma-spotify-text hover:text-white transition-colors disabled:opacity-50"
      >
        <RefreshCw size={18} class={loading ? 'animate-spin' : ''} />
      </button>
    </div>
  </div>

  {#if loading && rows.length === 0}
    <div class="flex items-center justify-center p-20"><RefreshCw class="animate-spin text-brand" size={32} /></div>
  {:else if visibleRows.length === 0}
    <p class="p-12 text-center text-muma-spotify-text">{$t('management.genres.overviewNone')}</p>
  {:else}
    <div class="overflow-x-auto">
      <table class="w-full text-left text-sm">
        <thead>
          <tr class="bg-white/5 text-muma-spotify-text text-[10px] uppercase tracking-wider">
            <th class="p-4">{$t('nav.genres')}</th>
            <th class="p-4">{$t('management.artists.tracks')}</th>
            <th class="p-4">{$t('management.genres.hardness')}</th>
            <th class="p-4">{$t('management.genres.parents')}</th>
            <th class="p-4">{$t('management.genres.rulesArtistShort')}</th>
            <th class="p-4">{$t('management.genres.rulesLabelShort')}</th>
            <th class="p-4 text-right">{$t('management.genres.actions')}</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-muma-spotify-panel/30">
          {#each visibleRows as row (row.id)}
            <tr class="hover:bg-white/5 transition-colors">
              <td class="p-4 font-bold">{row.name}</td>
              <td class="p-4 text-muma-spotify-text">{n(row.track_count)}</td>
              <td class="p-4 text-muma-spotify-text">{row.hardness ?? '—'}</td>
              <td class="p-4">
                {#each row.parents || [] as parent (parent)}
                  <span class="mr-1 px-2 py-0.5 bg-muma-spotify-dark rounded text-xs">{parent}</span>
                {:else}
                  <span class="text-muma-spotify-text">—</span>
                {/each}
              </td>
              <td class="p-4 text-muma-spotify-text">{n(row.artist_rule_count)}</td>
              <td class="p-4 text-muma-spotify-text">{n(row.label_rule_count)}</td>
              <td class="p-4 text-right">
                <button
                  type="button"
                  onclick={() => edit(row)}
                  class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs flex items-center gap-1 hover:scale-105 transition-transform ml-auto"
                >
                  <Pencil size={14} /> {$t('common.edit')}
                </button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>
