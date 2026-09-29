<script>
  /**
   * Browse by BPM: every track at a tempo, playable as a queue.
   *
   * The listener picks a tempo with a chip (150), a bar of the histogram, or a range typed in
   * two fields; the tolerance says how many BPM either side still count. "Betrouwbaar" keeps
   * only tempos MuMa trusts (a measurement, or a tag the old analyzer agrees with inside the
   * genre's band), and the genre picker narrows the list to one genre. MuMa answers with the
   * tracks' paths; they are resolved to songs through LMS the way the feeds are (`bpm.js`).
   *
   * Most tempos today come from an old analyzer with a coarse set of values, so a row shows
   * "≈152" for those and the page says once, quietly, what "≈" means -- it never nags. The
   * default tolerance comes from the server (±2), which is what lets "150" find the tracks that
   * analyzer rounded to 152. See docs/designs/bpm-browse/functional.md.
   */
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { Gauge, Info, ShieldCheck } from '@lucide/svelte';

  import { t, format } from './i18n/index.js';
  import { authParams, currentTrack, playerState } from './store.js';
  import { startQueue } from './queue.js';
  import TrackList from './TrackList.svelte';
  import ListEnd from './ListEnd.svelte';
  import SkeletonRows from './loading/SkeletonRows.svelte';
  import SectionState from './loading/SectionState.svelte';
  import {
    HISTOGRAM_RANGE,
    QUICK_BPMS,
    TOLERANCES,
    bpmContinuation,
    countNear,
    fetchBpmHistogram,
    fillBins,
    loadBpmPage,
    parseBpm,
    peakCount,
    selectionParams,
  } from './bpm.js';

  const { onnavigate } = $props();

  /** What is picked: a tempo (`bpm` ± `tol`) or a range (`from`..`to`), plus the two filters. */
  let selection = $state({ bpm: null, tol: null, from: null, to: null, reliable: false, genre: '' });
  let defaultTolerance = $state(2);
  let histogram = $state({ bins: [], genres: [] });
  let histogramStatus = $state('loading');

  let songs = $state([]);
  /** @type {'idle'|'loading'|'ready'|'error'} */
  let listStatus = $state('idle');
  let total = $state(0);
  let nextOffset = $state(null);
  let unresolved = $state(0);
  let approximate = $state(false);
  let loadingMore = $state(false);
  let pagedMore = $state(false);
  let loadSeq = 0;

  const num = (value) => $format.number(value);
  const params = $derived(selectionParams(selection));
  const tolerance = $derived(Number.isFinite(selection.tol) ? selection.tol : defaultTolerance);
  const toleranceChoices = $derived(
    [...new Set([...TOLERANCES, defaultTolerance])].sort((a, b) => a - b),
  );
  const bars = $derived(fillBins(histogram.bins));
  const barPeak = $derived(peakCount(histogram.bins));
  /** The window the list covers, for the header line and for lighting the matching bars. */
  const windowRange = $derived.by(() => {
    if (Number.isFinite(selection.bpm)) return [selection.bpm - tolerance, selection.bpm + tolerance];
    if (Number.isFinite(selection.from) || Number.isFinite(selection.to)) {
      return [selection.from ?? HISTOGRAM_RANGE.from, selection.to ?? HISTOGRAM_RANGE.to];
    }
    return null;
  });
  const title = $derived(
    Number.isFinite(selection.bpm)
      ? $t('bpm.queueName', { bpm: selection.bpm })
      : windowRange
        ? $t('bpm.rangeName', { from: Math.round(windowRange[0]), to: Math.round(windowRange[1]) })
        : $t('nav.bpm'),
  );
  const continuation = $derived(
    listStatus === 'ready' ? bpmContinuation(params, nextOffset, () => get(authParams)) : null,
  );

  /** Reload the histogram and genre choices for the current filters. */
  async function loadHistogram() {
    try {
      const body = await fetchBpmHistogram({ reliable: selection.reliable, genre: selection.genre || null });
      histogram = { bins: body.bins ?? [], genres: body.genres ?? [] };
      if (Number.isFinite(body.default_tolerance)) defaultTolerance = body.default_tolerance;
      histogramStatus = 'ready';
    } catch (error) {
      console.error('Could not load the BPM histogram', error);
      histogramStatus = 'error';
    }
  }

  /** Load the first page of the current selection; an answer for an older one is dropped. */
  async function loadList() {
    const seq = ++loadSeq;
    const current = params;
    const auth = get(authParams);
    pagedMore = false;
    if (!current || !auth) {
      listStatus = 'idle';
      songs = [];
      return;
    }
    listStatus = 'loading';
    const page = await loadBpmPage(current, auth);
    if (seq !== loadSeq) return;
    if (page.failed) {
      listStatus = 'error';
      return;
    }
    songs = page.songs;
    total = page.total;
    nextOffset = page.nextOffset;
    unresolved = page.unresolved;
    approximate = page.approximate;
    listStatus = 'ready';
  }

  /** "Meer laden": the next page, leaving out songs already shown. */
  async function loadMore() {
    const seq = loadSeq;
    const auth = get(authParams);
    if (loadingMore || !nextOffset || !params || !auth) return;
    loadingMore = true;
    try {
      const page = await loadBpmPage(params, auth, nextOffset);
      if (seq !== loadSeq || page.failed) return;
      const have = new Set(songs.map((song) => String(song.id)));
      songs = [...songs, ...page.songs.filter((song) => !have.has(String(song.id)))];
      nextOffset = page.nextOffset;
      unresolved += page.unresolved;
      approximate = approximate || page.approximate;
      pagedMore = true;
    } finally {
      loadingMore = false;
    }
  }

  /** Change the selection and reload what depends on it. */
  function apply(next, { histogramToo = false } = {}) {
    selection = { ...selection, ...next };
    loadList();
    if (histogramToo) loadHistogram();
  }

  function pickBpm(bpm) {
    if (selection.bpm === bpm) apply({ bpm: null });
    else apply({ bpm, from: null, to: null });
  }

  function setRange(bound, value) {
    apply({ bpm: null, [bound]: parseBpm(value) });
  }

  function playAll() {
    if (songs.length === 0) return;
    startQueue(songs, { name: title, continuation });
    currentTrack.set(songs[0]);
    playerState.update((s) => ({ ...s, playing: true }));
  }

  function barLit(bpm) {
    return windowRange !== null && bpm >= windowRange[0] - 0.5 && bpm <= windowRange[1] + 0.5;
  }

  onMount(() => {
    loadHistogram();
  });
</script>

<div class="p-4 sm:p-6 flex flex-col gap-6" data-testid="bpm-view">
  <header class="flex flex-wrap items-end justify-between gap-4">
    <div>
      <h1 class="text-3xl font-black tracking-tight text-white flex items-center gap-2">
        <Gauge size={26} class="text-brand" /> {$t('nav.bpm')}
      </h1>
      <p class="text-sm text-muma-spotify-text mt-1">{$t('bpm.subtitle')}</p>
    </div>
  </header>

  <section class="bg-black/40 p-4 rounded-xl border border-white/5 flex flex-col gap-4" aria-label={$t('bpm.filters')}>
    <div class="flex flex-col gap-2">
      <span class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text">{$t('bpm.tempo')}</span>
      <div class="flex flex-wrap gap-2" data-testid="bpm-chips">
        {#each QUICK_BPMS as bpm (bpm)}
          {@const active = selection.bpm === bpm}
          <button
            type="button"
            class="px-3 min-h-9 rounded-full text-xs font-bold transition-colors tabular-nums {active
              ? 'bg-brand text-black'
              : 'bg-muma-spotify-light text-white hover:bg-muma-spotify-hover'}"
            aria-pressed={active}
            onclick={() => pickBpm(bpm)}
          >
            {bpm}
            {#if histogramStatus === 'ready'}
              <span class="font-normal {active ? 'text-black/70' : 'text-muma-spotify-text'}">· {num(countNear(histogram.bins, bpm, tolerance))}</span>
            {/if}
          </button>
        {/each}
      </div>
    </div>

    <div class="flex flex-col lg:flex-row gap-4">
      <div class="flex flex-col gap-2">
        <span class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text">{$t('bpm.tolerance')}</span>
        <div class="flex gap-1 bg-black/40 border border-white/5 rounded-full p-1 w-fit" role="group" aria-label={$t('bpm.tolerance')}>
          {#each toleranceChoices as choice (choice)}
            <button
              type="button"
              class="px-3 py-1.5 rounded-full text-xs font-bold transition-colors tabular-nums {tolerance === choice
                ? 'bg-brand text-black'
                : 'text-muma-spotify-text hover:text-white'}"
              aria-pressed={tolerance === choice}
              onclick={() => apply({ tol: choice })}
            >±{choice}</button>
          {/each}
        </div>
      </div>

      <div class="flex flex-col gap-2 lg:w-64">
        <label for="bpm-from" class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text">{$t('bpm.range')}</label>
        <div class="flex items-center gap-2">
          <input
            id="bpm-from"
            type="number"
            inputmode="decimal"
            min="40"
            max="500"
            placeholder={$t('bpm.from')}
            aria-label={$t('bpm.from')}
            value={selection.from ?? ''}
            onchange={(event) => setRange('from', event.currentTarget.value)}
            class="w-full min-w-0 bg-muma-spotify-light text-white text-sm rounded-md px-3 min-h-11 border-none outline-none focus:outline focus:outline-1 focus:outline-brand placeholder:text-[#777]"
          />
          <span class="text-muma-spotify-subtle">–</span>
          <input
            id="bpm-to"
            type="number"
            inputmode="decimal"
            min="40"
            max="500"
            placeholder={$t('bpm.to')}
            aria-label={$t('bpm.to')}
            value={selection.to ?? ''}
            onchange={(event) => setRange('to', event.currentTarget.value)}
            class="w-full min-w-0 bg-muma-spotify-light text-white text-sm rounded-md px-3 min-h-11 border-none outline-none focus:outline focus:outline-1 focus:outline-brand placeholder:text-[#777]"
          />
        </div>
      </div>

      <div class="flex flex-col gap-2 lg:w-64">
        <label for="bpm-genre" class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text">{$t('bpm.genre')}</label>
        <select
          id="bpm-genre"
          value={selection.genre}
          onchange={(event) => apply({ genre: event.currentTarget.value }, { histogramToo: true })}
          class="w-full bg-muma-spotify-light text-white text-sm rounded-md px-3 min-h-11 border-none outline-none focus:outline focus:outline-1 focus:outline-brand"
        >
          <option value="">{$t('bpm.allGenres')}</option>
          {#each histogram.genres as genre (genre.name)}
            <option value={genre.name}>{genre.name} ({num(genre.count)})</option>
          {/each}
        </select>
      </div>

      <div class="flex flex-col gap-2">
        <span class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text">{$t('bpm.reliability')}</span>
        <button
          type="button"
          class="flex items-center gap-1.5 px-3 min-h-11 rounded-full text-xs font-bold transition-colors w-fit {selection.reliable
            ? 'bg-brand text-black'
            : 'bg-muma-spotify-light text-white hover:bg-muma-spotify-hover'}"
          aria-pressed={selection.reliable}
          title={$t('bpm.reliableHelp')}
          onclick={() => apply({ reliable: !selection.reliable }, { histogramToo: true })}
          data-testid="bpm-reliable"
        >
          <ShieldCheck size={14} /> {$t('bpm.reliable')}
        </button>
      </div>
    </div>
  </section>

  <section class="bg-black/40 p-5 rounded-xl border border-white/5" aria-label={$t('bpm.histogram')}>
    <h2 class="text-xs font-black uppercase tracking-widest text-muma-spotify-text mb-4">{$t('bpm.histogram')}</h2>
    {#if histogramStatus === 'error'}
      <SectionState status="error" onretry={loadHistogram} />
    {:else}
      <div class="flex items-end gap-px h-28" data-testid="bpm-histogram">
        {#each bars as bar (bar.bpm)}
          {@const lit = barLit(bar.bpm)}
          <button
            type="button"
            class="flex-1 min-w-px h-full flex flex-col justify-end group"
            aria-pressed={lit}
            aria-label={$t('bpm.bar', { bpm: bar.bpm, count: num(bar.count) })}
            title={$t('bpm.bar', { bpm: bar.bpm, count: num(bar.count) })}
            onclick={() => pickBpm(bar.bpm)}
          >
            <span
              class="block rounded-t-sm transition-colors {lit ? 'bg-brand' : 'bg-brand/50 group-hover:bg-brand/80'}"
              style="height: {(bar.count / barPeak) * 100}%"
            ></span>
          </button>
        {/each}
      </div>
      <div class="flex justify-between text-[10px] text-muma-spotify-subtle tabular-nums mt-1" aria-hidden="true">
        {#each [60, 100, 140, 180, 220, 260] as tick (tick)}<span>{tick}</span>{/each}
      </div>
      <p class="text-[10px] text-muma-spotify-subtle mt-2">{$t('bpm.histogramHint')}</p>
    {/if}
  </section>

  <section class="flex flex-col gap-4">
    {#if listStatus === 'idle'}
      <p class="text-sm text-muma-spotify-text">{$t('bpm.pickPrompt')}</p>
    {:else}
      <div class="flex items-center gap-6">
        {#if songs.length > 0}
          <button
            class="bg-brand text-black w-14 h-14 rounded-full flex items-center justify-center shadow-xl hover:scale-105 active:scale-95 transition cursor-pointer border-none shrink-0"
            onclick={playAll}
            title={$t('common.playAll')}
            data-testid="bpm-play"
          >
            <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor"><path d="M7 6v12l10-6z"></path></svg>
          </button>
        {/if}
        <div class="min-w-0">
          <h2 class="text-2xl font-black text-white truncate">{title}</h2>
          {#if listStatus === 'ready'}
            <p class="text-sm text-muma-spotify-text" data-testid="bpm-count">
              {$t('common.trackCount', { count: total })}
              {#if unresolved > 0}• {$t('feed.unresolved', { count: unresolved })}{/if}
            </p>
          {/if}
        </div>
      </div>

      {#if approximate}
        <p class="text-xs text-muma-spotify-text flex items-start gap-2" data-testid="bpm-coarse-note">
          <Info size={14} class="shrink-0 mt-0.5" /> {$t('bpm.coarseNote')}
        </p>
      {/if}

      {#if listStatus === 'loading'}
        <SkeletonRows count={8} />
      {:else if listStatus === 'error'}
        <SectionState status="error" onretry={loadList} />
      {:else if songs.length === 0}
        <p class="text-sm text-muma-spotify-text p-8 text-center">{selection.reliable ? $t('bpm.emptyReliable') : $t('bpm.empty')}</p>
      {:else}
        <TrackList tracks={songs} {continuation} sourceName={title} {onnavigate} />
        <ListEnd hasMore={Boolean(nextOffset)} ended={pagedMore} loading={loadingMore} onmore={loadMore} testid="bpm-load-more" />
      {/if}
    {/if}
  </section>
</div>
