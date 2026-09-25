<script>
  import { t, format } from '../../i18n/index.js';
  import { Disc, Clock, RefreshCw, ChevronLeft, ChevronRight } from '@lucide/svelte';

  export let tracks = [];
  export let total = 0;
  export let page = 1;
  export let limit = 100;
  export let loading = false;
  export let error = null;
  export let selectedTrack = null;
  export let onSelect;
  export let onPage;
  export let onSort = null;
  export let sort = 'created';
  export let direction = 'desc';

  $: pages = Math.max(1, Math.ceil(total / limit));

  // Sorting happens server-side: the table shows one page of a much longer list, so reordering
  // these hundred rows locally would be meaningless.
  //
  // First click on a column sorts descending, because "newest" and "fastest" are the interesting
  // ends; clicking the column that is already active flips it.
  function requestSort(key) {
    if (!onSort) return;
    onSort(key, sort === key && direction === 'desc' ? 'asc' : 'desc');
  }

  function arrow(key) {
    if (sort !== key) return '';
    return direction === 'desc' ? ' ↓' : ' ↑';
  }

  function duration(secs) {
    if (!secs) return '-';
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  }
</script>

<div class="flex flex-col">
  <div class="overflow-x-auto">
    <table class="w-full text-left text-sm border-collapse min-w-[720px]">
      <thead class="bg-muma-spotify-dark border-b border-white/10">
        <tr class="text-muma-spotify-text uppercase text-[10px] tracking-widest font-black">
          <th class="px-4 py-4">
            <button class="uppercase tracking-widest font-black hover:text-white" on:click={() => requestSort('title')}>
              {$t('track.title')}{arrow('title')}
            </button>
          </th>
          <th class="px-4 py-4">{$t('common.artist')}</th>
          <th class="px-4 py-4">{$t('library.label')}</th>
          <th class="px-4 py-4">{$t('nav.genres')}</th>
          <th class="px-4 py-4 text-right">
            <button class="uppercase tracking-widest font-black hover:text-white" on:click={() => requestSort('bpm')}>
              BPM{arrow('bpm')}
            </button>
          </th>
          <th class="px-4 py-4 text-right">
            <button class="uppercase tracking-widest font-black hover:text-white" on:click={() => requestSort('release')}>
              {$t('track.releaseDate')}{arrow('release')}
            </button>
          </th>
          <th class="px-4 py-4 text-right"><Clock size={14} class="inline" /></th>
        </tr>
      </thead>
      <tbody>
        {#if loading}
          <tr><td colspan="7" class="px-4 py-20 text-center text-muma-spotify-text">
            <div class="flex flex-col items-center gap-4">
              <RefreshCw class="animate-spin text-brand" size={32} />
              <span>{$t('library.loading')}</span>
            </div>
          </td></tr>
        {:else if error}
          <tr><td colspan="7" class="px-4 py-20 text-center">
            <div class="flex flex-col items-center gap-2">
              <span class="text-red-400 font-bold">{$t('library.loadFailed')}</span>
              <span class="text-xs text-muma-spotify-text max-w-md">{error}</span>
            </div>
          </td></tr>
        {:else if tracks.length === 0}
          <tr><td colspan="7" class="px-4 py-20 text-center text-muma-spotify-text">
            {$t('library.noTracksForFilters')}
          </td></tr>
        {:else}
          {#each tracks as track (track.id)}
            <tr
              class="border-b border-white/5 hover:bg-white/5 transition-colors cursor-pointer group {selectedTrack?.id === track.id ? 'bg-white/10' : ''}"
              on:click={() => onSelect(track)}
            >
              <td class="px-4 py-3">
                <div class="flex items-center gap-3">
                  <div class="w-9 h-9 bg-muma-spotify-light rounded flex items-center justify-center shrink-0">
                    <Disc size={18} class="text-muma-spotify-subtle" />
                  </div>
                  <span class="font-bold text-white truncate group-hover:text-brand transition-colors">{track.title}</span>
                </div>
              </td>
              <td class="px-4 py-3 text-muma-spotify-text truncate">{track.display_artist || track.artist || '-'}</td>
              <td class="px-4 py-3 text-muma-spotify-text truncate font-mono text-[11px]">{track.label || '-'}</td>
              <td class="px-4 py-3">
                <div class="flex flex-wrap gap-1">
                  {#each track.genres as genre (genre)}
                    <span class="text-[10px] bg-muma-spotify-raised px-1.5 py-0.5 rounded border border-white/5 text-muma-spotify-text">{genre}</span>
                  {/each}
                </div>
              </td>
              <td class="px-4 py-3 text-right text-muma-spotify-text font-mono tabular-nums">{track.bpm ? Math.round(track.bpm) : '-'}</td>
              <td class="px-4 py-3 text-right text-muma-spotify-text font-mono tabular-nums">{track.release_date || track.release_year || '-'}</td>
              <td class="px-4 py-3 text-right text-muma-spotify-text font-mono tabular-nums">{duration(track.duration_secs)}</td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>

  {#if !loading && !error && total > limit}
    <div class="flex items-center justify-between px-4 py-3 border-t border-white/5 text-xs text-muma-spotify-text">
      <span class="tabular-nums">{$t('management.library.totalTracks', { total: $format.number(total) })}</span>
      <div class="flex items-center gap-3">
        <button class="p-1 disabled:opacity-30 hover:text-white" disabled={page <= 1} on:click={() => onPage(page - 1)}>
          <ChevronLeft size={16} />
        </button>
        <span class="tabular-nums">{page} / {pages}</span>
        <button class="p-1 disabled:opacity-30 hover:text-white" disabled={page >= pages} on:click={() => onPage(page + 1)}>
          <ChevronRight size={16} />
        </button>
      </div>
    </div>
  {/if}
</div>
