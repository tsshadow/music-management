<script>
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

  $: pages = Math.max(1, Math.ceil(total / limit));

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
      <thead class="bg-[#121212] border-b border-white/10">
        <tr class="text-[#b3b3b3] uppercase text-[10px] tracking-widest font-black">
          <th class="px-4 py-4">Titel</th>
          <th class="px-4 py-4">Artiest</th>
          <th class="px-4 py-4">Label</th>
          <th class="px-4 py-4">Genre</th>
          <th class="px-4 py-4 text-right">BPM</th>
          <th class="px-4 py-4 text-right">Jaar</th>
          <th class="px-4 py-4 text-right"><Clock size={14} class="inline" /></th>
        </tr>
      </thead>
      <tbody>
        {#if loading}
          <tr><td colspan="7" class="px-4 py-20 text-center text-[#b3b3b3]">
            <div class="flex flex-col items-center gap-4">
              <RefreshCw class="animate-spin text-brand" size={32} />
              <span>Bibliotheek laden...</span>
            </div>
          </td></tr>
        {:else if error}
          <tr><td colspan="7" class="px-4 py-20 text-center">
            <div class="flex flex-col items-center gap-2">
              <span class="text-red-400 font-bold">Laden mislukt</span>
              <span class="text-xs text-[#b3b3b3] max-w-md">{error}</span>
            </div>
          </td></tr>
        {:else if tracks.length === 0}
          <tr><td colspan="7" class="px-4 py-20 text-center text-[#b3b3b3]">
            Geen tracks gevonden met deze filters.
          </td></tr>
        {:else}
          {#each tracks as track (track.id)}
            <tr
              class="border-b border-white/5 hover:bg-white/5 transition-colors cursor-pointer group {selectedTrack?.id === track.id ? 'bg-white/10' : ''}"
              on:click={() => onSelect(track)}
            >
              <td class="px-4 py-3">
                <div class="flex items-center gap-3">
                  <div class="w-9 h-9 bg-[#282828] rounded flex items-center justify-center shrink-0">
                    <Disc size={18} class="text-[#535353]" />
                  </div>
                  <span class="font-bold text-white truncate group-hover:text-brand transition-colors">{track.title}</span>
                </div>
              </td>
              <td class="px-4 py-3 text-[#b3b3b3] truncate">{track.artist || '-'}</td>
              <td class="px-4 py-3 text-[#b3b3b3] truncate font-mono text-[11px]">{track.label || '-'}</td>
              <td class="px-4 py-3">
                <div class="flex flex-wrap gap-1">
                  {#each track.genres as genre (genre)}
                    <span class="text-[10px] bg-[#242424] px-1.5 py-0.5 rounded border border-white/5 text-[#b3b3b3]">{genre}</span>
                  {/each}
                </div>
              </td>
              <td class="px-4 py-3 text-right text-[#b3b3b3] font-mono tabular-nums">{track.bpm ? Math.round(track.bpm) : '-'}</td>
              <td class="px-4 py-3 text-right text-[#b3b3b3] font-mono tabular-nums">{track.release_year || '-'}</td>
              <td class="px-4 py-3 text-right text-[#b3b3b3] font-mono tabular-nums">{duration(track.duration_secs)}</td>
            </tr>
          {/each}
        {/if}
      </tbody>
    </table>
  </div>

  {#if !loading && !error && total > limit}
    <div class="flex items-center justify-between px-4 py-3 border-t border-white/5 text-xs text-[#b3b3b3]">
      <span class="tabular-nums">{total.toLocaleString('nl-NL')} tracks</span>
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
