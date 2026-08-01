<script>
  import { t } from '../../i18n/index.js';
  import { PieChart, Activity, Calendar, Users, Tag, AlertTriangle } from '@lucide/svelte';

  export let genreDistribution = [];  // [{genre, state, count}]
  export let bpmHistogram = [];       // [{bucket_start, count}]
  export let yearHistogram = [];      // [{year, count}]
  export let topArtists = [];         // [{artist, count}]
  export let topLabels = [];          // [{label, count}]
  export let bpmBucket = 5;
  export let onFilterAdd;             // (key, value) => void

  const peak = (rows, key = 'count') =>
    rows.reduce((max, row) => Math.max(max, row[key]), 0) || 1;
</script>

<div class="p-6 grid grid-cols-1 xl:grid-cols-2 gap-6">

  <div class="bg-black/40 p-5 rounded-xl border border-white/5">
    <h3 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-5 flex items-center gap-2">
      <PieChart size={15} class="text-brand" /> {$t('library.genreDistribution')}
    </h3>
    {#if genreDistribution.length === 0}
      <p class="text-xs text-[#535353]">{$t('library.noGenresInSelection')}</p>
    {:else}
      <div class="flex flex-col gap-3 max-h-80 overflow-y-auto pr-2">
        {#each genreDistribution as row (row.genre)}
          <button class="flex flex-col gap-1 text-left w-full" on:click={() => onFilterAdd('genre', row.genre)}>
            <div class="flex justify-between text-xs">
              <span class="{row.state === 'unknown' ? 'text-[#8a8a8a] italic' : 'text-white'} font-bold truncate">{row.genre}</span>
              <span class="text-[#b3b3b3] tabular-nums shrink-0 ml-2">{row.count.toLocaleString('nl-NL')}</span>
            </div>
            <div class="h-1.5 w-full bg-white/5 rounded-full overflow-hidden">
              <div class="h-full bg-brand rounded-full" style="width: {(row.count / peak(genreDistribution)) * 100}%"></div>
            </div>
          </button>
        {/each}
      </div>
    {/if}
  </div>

  <div class="bg-black/40 p-5 rounded-xl border border-white/5">
    <h3 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-2 flex items-center gap-2">
      <Activity size={15} class="text-blue-400" /> {$t('library.bpmDistribution')}
    </h3>
    <p class="text-[10px] text-yellow-600/90 flex items-start gap-1.5 mb-4">
      <AlertTriangle size={12} class="shrink-0 mt-0.5" />
      {$t('library.bpmCaveat')}
    </p>
    {#if bpmHistogram.length === 0}
      <p class="text-xs text-[#535353]">{$t('library.noBpmInSelection')}</p>
    {:else}
      <div class="flex items-end gap-0.5 h-48">
        {#each bpmHistogram as bar (bar.bucket_start)}
          <div
            class="flex-1 min-w-[2px] bg-brand/25 hover:bg-brand/60 transition-colors rounded-t relative group"
            style="height: {(bar.count / peak(bpmHistogram)) * 100}%"
          >
            <div class="absolute -top-7 left-1/2 -translate-x-1/2 bg-white text-black text-[9px] font-bold px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">
              {bar.bucket_start}-{bar.bucket_start + bpmBucket}: {bar.count.toLocaleString('nl-NL')}
            </div>
          </div>
        {/each}
      </div>
      <div class="flex justify-between mt-2 text-[10px] text-[#535353] font-mono tabular-nums">
        <span>{bpmHistogram[0].bucket_start}</span>
        <span>{bpmHistogram[bpmHistogram.length - 1].bucket_start + bpmBucket}</span>
      </div>
    {/if}
  </div>

  <div class="bg-black/40 p-5 rounded-xl border border-white/5">
    <h3 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-5 flex items-center gap-2">
      <Calendar size={15} class="text-brand" /> {$t('library.releaseYears')}
    </h3>
    {#if yearHistogram.length === 0}
      <p class="text-xs text-[#535353]">{$t('library.noYearsInSelection')}</p>
    {:else}
      <div class="flex items-end gap-0.5 h-40">
        {#each yearHistogram as bar (bar.year)}
          <div class="flex-1 min-w-[2px] bg-blue-400/25 hover:bg-blue-400/60 transition-colors rounded-t relative group"
               style="height: {(bar.count / peak(yearHistogram)) * 100}%">
            <div class="absolute -top-7 left-1/2 -translate-x-1/2 bg-white text-black text-[9px] font-bold px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">
              {bar.year}: {bar.count.toLocaleString('nl-NL')}
            </div>
          </div>
        {/each}
      </div>
      <div class="flex justify-between mt-2 text-[10px] text-[#535353] font-mono tabular-nums">
        <span>{yearHistogram[0].year}</span>
        <span>{yearHistogram[yearHistogram.length - 1].year}</span>
      </div>
    {/if}
  </div>

  <div class="bg-black/40 p-5 rounded-xl border border-white/5 grid grid-cols-1 sm:grid-cols-2 gap-6">
    <div>
      <h3 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-4 flex items-center gap-2">
        <Users size={15} class="text-brand" /> {$t('library.topArtists')}
      </h3>
      <div class="flex flex-col gap-2">
        {#each topArtists as row (row.artist)}
          <button class="flex justify-between text-xs gap-2 text-left hover:text-brand transition-colors"
                  on:click={() => onFilterAdd('artist', row.artist)}>
            <span class="truncate">{row.artist}</span>
            <span class="text-[#b3b3b3] tabular-nums shrink-0">{row.count.toLocaleString('nl-NL')}</span>
          </button>
        {/each}
        {#if topArtists.length === 0}
          <p class="text-xs text-[#535353]">{$t('library.noArtistsInSelection')}</p>
        {/if}
      </div>
    </div>
    <div>
      <h3 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-4 flex items-center gap-2">
        <Tag size={15} class="text-blue-400" /> {$t('library.topLabels')}
      </h3>
      <div class="flex flex-col gap-2">
        {#each topLabels as row (row.label)}
          <button class="flex justify-between text-xs gap-2 text-left hover:text-brand transition-colors"
                  on:click={() => onFilterAdd('label', row.label)}>
            <span class="truncate">{row.label}</span>
            <span class="text-[#b3b3b3] tabular-nums shrink-0">{row.count.toLocaleString('nl-NL')}</span>
          </button>
        {/each}
        {#if topLabels.length === 0}
          <p class="text-xs text-[#535353]">{$t('library.noLabelsInSelection')}</p>
        {/if}
      </div>
    </div>
  </div>
</div>
