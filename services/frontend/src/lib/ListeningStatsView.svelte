<script>
  /**
   * What you listened to, as opposed to what is in the library.
   *
   * The page leads with the caveat rather than burying it. Most of the recorded
   * history is not linked to a library track, and only a fraction of it ever
   * recorded how long it played, so the totals and the rankings are counting
   * different populations. Both facts sit above the charts, in the same type as
   * the numbers they qualify -- a footnote would let a reader take the top-ten
   * lists for the whole story, which is the one mistake this page can cause.
   *
   * Charts are bars made of divs, like AnalyticsPanel: a listening page is not
   * worth a charting dependency, and every value is in the DOM as text as well,
   * so hovering is not the only way to read it.
   */
  import { onMount } from 'svelte';
  import { Clock, Headphones, ListMusic, Radio, Tag, TriangleAlert, Users } from '@lucide/svelte';

  import { t } from './i18n/index.js';
  import {
    DEFAULT_PERIOD,
    PERIODS,
    bucketLabel,
    loadListening,
    measuredPercent,
    peak,
    splitDuration,
    unmatchedPercent,
  } from './listeningStats.js';

  const { onnavigate } = $props();

  let period = $state(DEFAULT_PERIOD);
  let data = $state(null);
  let isLoading = $state(true);

  const summary = $derived(data?.summary ?? null);
  const buckets = $derived(data?.timeline?.buckets ?? []);
  const hours = $derived(data?.clock?.hours ?? []);
  const weekdays = $derived(data?.clock?.weekdays ?? []);
  const sources = $derived(data?.sources?.sources ?? []);
  const topTracks = $derived(data?.tracks?.tracks ?? []);
  const topArtists = $derived(data?.artists?.artists ?? []);
  const topLabels = $derived(data?.labels?.labels ?? []);

  const unmatched = $derived(unmatchedPercent(summary));
  const measured = $derived(measuredPercent(summary));
  const listened = $derived(splitDuration(summary?.estimated_secs));

  const num = (value) => (value ?? 0).toLocaleString('nl-NL');

  async function load() {
    isLoading = true;
    data = await loadListening(period);
    isLoading = false;
  }

  onMount(load);

  function selectPeriod(id) {
    if (id === period) return;
    period = id;
    load();
  }
</script>

<div class="p-4 sm:p-6 flex flex-col gap-6">

  <header class="flex flex-wrap items-end justify-between gap-4">
    <div>
      <h1 class="text-3xl font-black tracking-tight text-white">{$t('listening.title')}</h1>
      <p class="text-sm text-[#b3b3b3] mt-1">{$t('listening.subtitle')}</p>
    </div>
    <div class="flex gap-1 bg-black/40 border border-white/5 rounded-full p-1">
      {#each PERIODS as option (option.id)}
        <button
          class="px-4 py-1.5 rounded-full text-xs font-bold transition-colors {period === option.id
            ? 'bg-brand text-black'
            : 'text-[#b3b3b3] hover:text-white'}"
          onclick={() => selectPeriod(option.id)}
        >{$t(`listening.period.${option.id}`)}</button>
      {/each}
    </div>
  </header>

  {#if isLoading}
    <p class="text-sm text-[#535353]">{$t('listening.loading')}</p>
  {:else if !summary}
    <p class="text-sm text-[#535353]">{$t('listening.unavailable')}</p>
  {:else if summary.listens === 0}
    <p class="text-sm text-[#535353]">{$t('listening.empty')}</p>
  {:else}

    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <p class="text-[10px] font-black uppercase tracking-widest text-[#b3b3b3] flex items-center gap-1.5">
          <Headphones size={13} class="text-brand" /> {$t('listening.tile.listens')}
        </p>
        <p class="text-3xl font-black text-white mt-2 tabular-nums">{num(summary.listens)}</p>
        <p class="text-[11px] text-[#535353] mt-1">{$t('listening.tile.matchedOf', { matched: num(summary.matched) })}</p>
      </div>
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <p class="text-[10px] font-black uppercase tracking-widest text-[#b3b3b3] flex items-center gap-1.5">
          <ListMusic size={13} class="text-brand" /> {$t('listening.tile.tracks')}
        </p>
        <p class="text-3xl font-black text-white mt-2 tabular-nums">{num(summary.tracks)}</p>
        <p class="text-[11px] text-[#535353] mt-1">{$t('listening.tile.matchedOnly')}</p>
      </div>
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <p class="text-[10px] font-black uppercase tracking-widest text-[#b3b3b3] flex items-center gap-1.5">
          <Users size={13} class="text-brand" /> {$t('listening.tile.artists')}
        </p>
        <p class="text-3xl font-black text-white mt-2 tabular-nums">{num(summary.artists)}</p>
        <p class="text-[11px] text-[#535353] mt-1">{$t('listening.tile.matchedOnly')}</p>
      </div>
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <p class="text-[10px] font-black uppercase tracking-widest text-[#b3b3b3] flex items-center gap-1.5">
          <Clock size={13} class="text-brand" /> {$t('listening.tile.time')}
        </p>
        <p class="text-3xl font-black text-white mt-2 tabular-nums">
          {num(listened.hours)}<span class="text-lg">{$t('listening.hoursShort')}</span>
          {listened.minutes}<span class="text-lg">{$t('listening.minutesShort')}</span>
        </p>
        <p class="text-[11px] text-[#535353] mt-1">{$t('listening.tile.estimated')}</p>
      </div>
    </div>

    <div class="bg-yellow-500/5 border border-yellow-500/20 rounded-xl p-4 flex items-start gap-3">
      <TriangleAlert size={16} class="text-yellow-500/80 shrink-0 mt-0.5" />
      <div class="text-xs text-[#d0d0d0] leading-relaxed">
        <p>{$t('listening.caveat.unmatched', { percent: unmatched, count: num(summary.unmatched) })}</p>
        <p class="mt-1">{$t('listening.caveat.measured', { percent: measured, count: num(summary.measured_listens) })}</p>
      </div>
    </div>

    <div class="bg-black/40 p-5 rounded-xl border border-white/5">
      <h2 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-5">{$t('listening.timeline')}</h2>
      {#if buckets.length === 0}
        <p class="text-xs text-[#535353]">{$t('listening.empty')}</p>
      {:else}
        <div class="flex items-end gap-0.5 h-40">
          {#each buckets as bar (bar.bucket)}
            <div class="flex-1 min-w-[3px] flex flex-col justify-end h-full group relative">
              <div
                class="bg-white/10 rounded-t-sm"
                style="height: {(bar.unmatched / peak(buckets)) * 100}%"
              ></div>
              <div
                class="bg-brand/70 group-hover:bg-brand transition-colors"
                style="height: {(bar.matched / peak(buckets)) * 100}%"
              ></div>
              <div class="absolute -top-8 left-1/2 -translate-x-1/2 bg-white text-black text-[9px] font-bold px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">
                {bar.bucket}: {num(bar.listens)}
              </div>
            </div>
          {/each}
        </div>
        <div class="flex justify-between mt-2 text-[10px] text-[#535353] font-mono tabular-nums">
          <span>{bucketLabel(buckets[0].bucket, data.bucket)}</span>
          <span>{bucketLabel(buckets[buckets.length - 1].bucket, data.bucket)}</span>
        </div>
        <p class="text-[10px] text-[#535353] mt-3">{$t('listening.timelineLegend')}</p>
      {/if}
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <h2 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-5">{$t('listening.clock')}</h2>
        <div class="flex items-end gap-0.5 h-32">
          {#each hours as count, hour (hour)}
            <div class="flex-1 flex flex-col justify-end h-full group relative">
              <div class="bg-brand/50 group-hover:bg-brand transition-colors rounded-t-sm" style="height: {(count / peak(hours.map((n) => ({ listens: n })))) * 100}%"></div>
              <div class="absolute -top-7 left-1/2 -translate-x-1/2 bg-white text-black text-[9px] font-bold px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-10">
                {String(hour).padStart(2, '0')}:00 — {num(count)}
              </div>
            </div>
          {/each}
        </div>
        <div class="flex justify-between mt-2 text-[10px] text-[#535353] font-mono tabular-nums">
          <span>00:00</span><span>12:00</span><span>23:00</span>
        </div>
      </div>

      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <h2 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-5">{$t('listening.weekdays')}</h2>
        <div class="flex flex-col gap-2.5">
          {#each weekdays as count, day (day)}
            <div class="flex items-center gap-3">
              <span class="text-[11px] text-[#b3b3b3] w-8 shrink-0">{$t(`listening.weekday.${day}`)}</span>
              <div class="h-2 flex-1 bg-white/5 rounded-full overflow-hidden">
                <div class="h-full bg-brand rounded-full" style="width: {(count / peak(weekdays.map((n) => ({ listens: n })))) * 100}%"></div>
              </div>
              <span class="text-[11px] text-[#b3b3b3] tabular-nums w-12 text-right shrink-0">{num(count)}</span>
            </div>
          {/each}
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-6">
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <h2 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-1">{$t('listening.topTracks')}</h2>
        <p class="text-[10px] text-[#535353] mb-4">{$t('listening.matchedOnlyNote')}</p>
        {#if topTracks.length === 0}
          <p class="text-xs text-[#535353]">{$t('listening.empty')}</p>
        {:else}
          <ol class="flex flex-col gap-2.5">
            {#each topTracks as track, index (track.track_id)}
              <li class="flex items-center gap-3">
                <span class="text-[11px] text-[#535353] tabular-nums w-4 shrink-0">{index + 1}</span>
                <span class="flex-1 min-w-0">
                  <span class="block text-xs text-white font-bold truncate">{track.title}</span>
                  <span class="block text-[11px] text-[#b3b3b3] truncate">{track.artist ?? $t('listening.unknownArtist')}</span>
                </span>
                <span class="text-xs text-[#b3b3b3] tabular-nums shrink-0">{num(track.listens)}</span>
              </li>
            {/each}
          </ol>
        {/if}
      </div>

      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <h2 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-1">{$t('listening.topArtists')}</h2>
        <p class="text-[10px] text-[#535353] mb-4">{$t('listening.matchedOnlyNote')}</p>
        {#if topArtists.length === 0}
          <p class="text-xs text-[#535353]">{$t('listening.empty')}</p>
        {:else}
          <ol class="flex flex-col gap-2.5">
            {#each topArtists as artist, index (artist.artist_id)}
              <li class="flex items-center gap-3">
                <span class="text-[11px] text-[#535353] tabular-nums w-4 shrink-0">{index + 1}</span>
                <button
                  class="flex-1 min-w-0 text-left text-xs text-white font-bold truncate hover:underline"
                  onclick={() => onnavigate?.(`artist:${artist.artist_id}`)}
                >{artist.artist}</button>
                <span class="text-xs text-[#b3b3b3] tabular-nums shrink-0">{num(artist.listens)}</span>
              </li>
            {/each}
          </ol>
        {/if}
      </div>

      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <h2 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-1 flex items-center gap-1.5">
          <Tag size={13} class="text-brand" /> {$t('listening.topLabels')}
        </h2>
        <p class="text-[10px] text-[#535353] mb-4">{$t('listening.labelsNote')}</p>
        {#if topLabels.length === 0}
          <p class="text-xs text-[#535353]">{$t('listening.empty')}</p>
        {:else}
          <ol class="flex flex-col gap-2.5">
            {#each topLabels as label, index (label.label_id)}
              <li class="flex items-center gap-3">
                <span class="text-[11px] text-[#535353] tabular-nums w-4 shrink-0">{index + 1}</span>
                <button
                  class="flex-1 min-w-0 text-left text-xs text-white font-bold truncate hover:underline"
                  onclick={() => onnavigate?.(`label:${label.label}`)}
                >{label.label}</button>
                <span class="text-xs text-[#b3b3b3] tabular-nums shrink-0">{num(label.listens)}</span>
              </li>
            {/each}
          </ol>
        {/if}
      </div>
    </div>

    {#if sources.length > 0}
      <div class="bg-black/40 p-5 rounded-xl border border-white/5">
        <h2 class="text-xs font-black uppercase tracking-widest text-[#b3b3b3] mb-1 flex items-center gap-1.5">
          <Radio size={13} class="text-brand" /> {$t('listening.sources')}
        </h2>
        <p class="text-[10px] text-[#535353] mb-4">{$t('listening.sourcesNote')}</p>
        <div class="flex flex-col gap-2.5">
          {#each sources as row (row.source)}
            <div class="flex items-center gap-3">
              <span class="text-[11px] text-white w-40 shrink-0 truncate">{row.source}</span>
              <div class="h-2 flex-1 bg-white/5 rounded-full overflow-hidden">
                <div class="h-full bg-brand rounded-full" style="width: {(row.listens / peak(sources)) * 100}%"></div>
              </div>
              <span class="text-[11px] text-[#b3b3b3] tabular-nums w-16 text-right shrink-0">{num(row.listens)}</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  {/if}
</div>
