<script>
  import { t, locale } from '../../i18n/index.js';
  import { Info, Music, RefreshCw, Download, Calendar, Hash, FileAudio } from '@lucide/svelte';

  export let track = null;
  export let onRerunParse;
  export let onRedownload;

  function duration(secs) {
    if (!secs) return null;
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  }
</script>

<div class="w-full lg:w-80 shrink-0 bg-[#181818] border border-white/5 rounded-xl overflow-hidden lg:sticky lg:top-4 flex flex-col">
  {#if track}
    <div class="p-6 flex flex-col gap-5">
      <div class="aspect-square bg-[#282828] rounded-xl flex items-center justify-center border border-white/10">
        <Music size={56} class="text-[#535353]" />
      </div>

      <div class="flex flex-col gap-1">
        <h2 class="text-lg font-black text-white leading-tight">{track.title}</h2>
        {#if track.artist}<p class="text-brand font-bold text-sm">{track.display_artist || track.artist}</p>{/if}
        {#if track.label}<p class="text-[#b3b3b3] text-xs">{track.label}</p>{/if}
      </div>

      <div class="grid grid-cols-2 gap-3">
        {#if track.bpm}
          <div class="bg-white/5 p-3 rounded-lg border border-white/5">
            <span class="text-[9px] uppercase tracking-widest text-[#b3b3b3] block mb-1">BPM</span>
            <span class="text-lg font-black font-mono tabular-nums">{Math.round(track.bpm)}</span>
          </div>
        {/if}
        {#if track.release_date || track.release_year}
          <div class="bg-white/5 p-3 rounded-lg border border-white/5">
            <span class="text-[9px] uppercase tracking-widest text-[#b3b3b3] block mb-1">
              {track.release_date && track.release_date.length > 4 ? $t('track.releaseDate') : $t('filter.year')}
            </span>
            <span class="text-lg font-black font-mono tabular-nums">{track.release_date || track.release_year}</span>
          </div>
        {/if}
        {#if duration(track.duration_secs)}
          <div class="bg-white/5 p-3 rounded-lg border border-white/5">
            <span class="text-[9px] uppercase tracking-widest text-[#b3b3b3] block mb-1">{$t('library.duration')}</span>
            <span class="text-lg font-black font-mono tabular-nums">{duration(track.duration_secs)}</span>
          </div>
        {/if}
      </div>

      {#if track.genres && track.genres.length > 0}
        <div>
          <h3 class="text-[10px] uppercase tracking-widest text-[#b3b3b3] font-bold mb-2">{$t('nav.genres')}</h3>
          <div class="flex flex-wrap gap-1">
            {#each track.genres as genre (genre)}
              <span class="text-[10px] bg-[#242424] px-2 py-0.5 rounded border border-white/5 text-[#b3b3b3]">{genre}</span>
            {/each}
          </div>
        </div>
      {/if}

      <div class="flex flex-col gap-2 pt-3 border-t border-white/5 text-[10px] text-[#535353]">
        {#if track.created_at}
          <p class="flex items-center gap-2"><Calendar size={12} /> {$t('library.addedOn', { date: new Date(track.created_at).toLocaleDateString($locale) })}</p>
        {/if}
        <p class="flex items-center gap-2"><Hash size={12} /> ID: {track.id}</p>
        {#if track.file_path}
          <p class="flex items-start gap-2 break-all"><FileAudio size={12} class="shrink-0 mt-0.5" /> {track.file_path}</p>
        {/if}
      </div>

      <div class="flex flex-col gap-2">
        <button
          class="flex items-center justify-center gap-2 text-xs font-bold bg-white/5 hover:bg-white/10 border border-white/10 rounded-full py-2 transition-colors"
          on:click={() => onRerunParse(track)}
        >
          <RefreshCw size={14} /> {$t('library.reanalyse')}
        </button>
        <button
          class="flex items-center justify-center gap-2 text-xs font-bold bg-white/5 hover:bg-white/10 border border-white/10 rounded-full py-2 transition-colors"
          on:click={() => onRedownload(track)}
        >
          <Download size={14} /> {$t('library.redownload')}
        </button>
      </div>
    </div>
  {:else}
    <div class="flex-1 min-h-[280px] flex flex-col items-center justify-center p-8 text-center text-[#b3b3b3] gap-4">
      <div class="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center">
        <Info size={32} />
      </div>
      <div>
        <h4 class="text-white font-bold mb-1">{$t('library.noTrackSelected')}</h4>
        <p class="text-xs">{$t('library.noTrackSelectedHelp')}</p>
      </div>
    </div>
  {/if}
</div>
