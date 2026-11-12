<script>
  /**
   * MuMa Wrapped: one period of listening as a stack of cards, for you (the User tab) or for the
   * whole library (the Library tab). The address is `/wrapped/<period>/<tab>`; switching the tab
   * or the period rewrites it in place, so the back button leaves Wrapped instead of stepping
   * through every tab you looked at (docs/designs/wrapped-page/technical.md).
   *
   * The server decides what each card says and whether it is shown: only `ok` cards are drawn,
   * and the coverage card at the end lists the rest with their reason.
   */
  import { onMount } from 'svelte';
  import { t, currentLocale } from '../i18n/index.js';
  import { authParams, currentTrack, playerState } from '../store.js';
  import { startQueue } from '../queue.js';
  import { resolveFeedChunk } from '../feeds.js';
  import { resolveArtistView } from '../homeRankings.js';
  import { fetchGenreTints, tintFor } from '../genreTints.js';
  import { notify } from '../notifications.js';
  import { platform as defaultPlatform } from '../platform/index.js';
  import { viewToPath } from '../router.js';
  import {
    TABS,
    describeCard,
    describeCoverage,
    formatters,
    hasListens,
    leadingGenre,
    loadPeriods,
    loadTab,
    parseWrappedRoute,
    periodLabel,
    pickerYears,
    playablePaths,
    rangeKey,
    visibleCards,
    wrappedView,
  } from './wrapped.js';
  import { renderShareCard, shareFileName } from './shareCard.js';
  import HeroCard from './HeroCard.svelte';
  import RankCard from './RankCard.svelte';
  import BarsCard from './BarsCard.svelte';
  import ClockCard from './ClockCard.svelte';
  import HeatmapCard from './HeatmapCard.svelte';
  import FactCard from './FactCard.svelte';
  import CoverageCard from './CoverageCard.svelte';

  const {
    route = '',
    onnavigate = () => {},
    fetcher = undefined,
    wait = undefined,
    platform = defaultPlatform,
    renderImage = renderShareCard,
  } = $props();

  const parsed = $derived(parseWrappedRoute(route));
  const periodKey = $derived(parsed.periodKey);
  const tab = $derived(parsed.tab);

  let years = $state([]);
  let tints = $state({});
  /** 'loading' | 'computing' | 'ok' | 'unavailable' */
  let status = $state('loading');
  let payload = $state(null);
  let customOpen = $state(false);
  let customFrom = $state('');
  let customTo = $state('');
  let customInvalid = $state(false);
  let attempt = $state(0);

  const f = $derived(formatters($t, currentLocale()));
  const label = $derived(payload ? periodLabel(payload.period, f) : '');
  const cards = $derived(
    visibleCards(payload).map((card) => ({
      card,
      face: describeCard(card, f, { scope: tab, period: label }),
      tint: tintFor(tints, leadingGenre(card)),
    })),
  );
  const coverage = $derived(payload ? describeCoverage(payload.coverage, f) : null);
  const emptyUser = $derived(status === 'ok' && tab === 'user' && !hasListens(payload));
  const yearOptions = $derived(pickerYears(years, periodKey));
  const isRange = $derived(periodKey.includes('_'));

  /** Moves to another period or tab without a new history entry. */
  function go(nextKey, nextTab) {
    const view = wrappedView(nextKey, nextTab);
    const path = viewToPath({ view, loggedIn: true });
    if (path && typeof window !== 'undefined') window.history.replaceState({}, '', path);
    onnavigate(view);
  }

  onMount(() => {
    // The bare '/wrapped' becomes the running year's User tab, in place.
    if (!route) go(periodKey, tab);
    loadPeriods(fetcher).then((answer) => (years = answer));
    fetchGenreTints()
      .then((answer) => (tints = answer ?? {}))
      .catch(() => {});
  });

  $effect(() => {
    const key = periodKey;
    const which = tab;
    void attempt;
    let stale = false;
    status = 'loading';
    payload = null;
    loadTab(which, key, {
      fetcher,
      wait,
      onComputing: () => {
        if (!stale) status = 'computing';
      },
    }).then((answer) => {
      if (stale) return;
      if (answer.state === 'ok') {
        payload = answer.payload;
        status = 'ok';
      } else {
        status = 'unavailable';
      }
    });
    return () => {
      stale = true;
    };
  });

  /** Applies the custom range, or says why it cannot. */
  function applyRange() {
    const key = rangeKey(customFrom, customTo);
    customInvalid = !key;
    if (!key) return;
    customOpen = false;
    go(key, tab);
  }

  /** The period picker's change: a year, or the custom range form. */
  function pickPeriod(value) {
    if (value === 'custom') {
      customOpen = true;
      return;
    }
    customOpen = false;
    go(value, tab);
  }

  /** Opens what a card entry points at. An artist that is not in the library opens a search. */
  async function openLink(link) {
    if (!link?.name) return;
    if (link.type === 'artist') {
      const view = await resolveArtistView(link.name);
      onnavigate(view ?? `search:${link.name}`);
      return;
    }
    onnavigate(`${link.type}:${link.name}`);
  }

  /** Plays the tracks of a card, in its order. */
  async function playCard(face) {
    const card = cards.find((entry) => entry.face.id === face.id)?.card;
    const paths = playablePaths(card);
    if (paths.length === 0) return;
    const { songs } = await resolveFeedChunk(paths, $authParams);
    if (songs.length === 0) {
      notify.error($t('wrapped.playFailed'));
      return;
    }
    startQueue(songs, { name: `${$t('wrapped.title')} ${label}` });
    currentTrack.set(songs[0]);
    playerState.update((s) => ({ ...s, playing: true }));
  }

  /** Shares one card as an image: no username, no server address. */
  async function shareCard(face, tint) {
    try {
      const dataUrl = renderImage(face, { period: label, brand: $t('wrapped.brand'), tint });
      const result = await platform.system.share({
        dataUrl,
        title: `${$t('wrapped.brand')} ${label}`,
        fileName: shareFileName(periodKey, face.id),
      });
      if (result === 'saved') notify.success($t('wrapped.shareSaved'));
    } catch (err) {
      console.error('Could not share a Wrapped card:', err);
      notify.error($t('wrapped.shareFailed'));
    }
  }
</script>

<div class="flex flex-col gap-6" data-testid="wrapped-view">
  <header class="flex flex-col gap-4">
    <div class="flex flex-col gap-1">
      <h1 class="m-0 text-3xl md:text-5xl font-black">{$t('wrapped.title')}</h1>
      <p class="m-0 text-muma-spotify-text">{$t('wrapped.subtitle')}</p>
    </div>
    <div class="flex flex-wrap items-center gap-3">
      <div class="flex gap-2" role="group" aria-label={$t('wrapped.tabs.label')}>
        {#each TABS as entry (entry)}
          <button
            type="button"
            class="rounded-full px-4 py-1.5 text-sm font-bold border-none cursor-pointer {entry === tab ? 'bg-brand text-black' : 'bg-muma-spotify-light text-white hover:bg-muma-spotify-hover'}"
            aria-pressed={entry === tab}
            onclick={() => go(periodKey, entry)}
          >{$t(`wrapped.tabs.${entry}`)}</button>
        {/each}
      </div>
      <select
        class="bg-muma-spotify-light border border-white/10 rounded-full px-4 py-1.5 text-sm text-white focus:outline-none focus:border-brand"
        aria-label={$t('wrapped.period.label')}
        value={customOpen || isRange ? 'custom' : periodKey}
        onchange={(event) => pickPeriod(event.currentTarget.value)}
      >
        {#each yearOptions as year (year)}
          <option value={String(year)}>{year}</option>
        {/each}
        <option value="custom">{$t('wrapped.period.custom')}</option>
      </select>
    </div>
    {#if customOpen}
      <form
        class="flex flex-wrap items-end gap-3"
        data-testid="wrapped-range"
        onsubmit={(event) => {
          event.preventDefault();
          applyRange();
        }}
      >
        <label class="flex flex-col gap-1 text-sm text-muma-spotify-text">
          {$t('wrapped.period.from')}
          <input type="date" class="bg-muma-spotify-light border border-white/10 rounded-md px-3 py-1.5 text-white" bind:value={customFrom} />
        </label>
        <label class="flex flex-col gap-1 text-sm text-muma-spotify-text">
          {$t('wrapped.period.to')}
          <input type="date" class="bg-muma-spotify-light border border-white/10 rounded-md px-3 py-1.5 text-white" bind:value={customTo} />
        </label>
        <button type="submit" class="rounded-full bg-white text-black font-bold px-4 py-1.5 border-none cursor-pointer">{$t('wrapped.period.apply')}</button>
        {#if customInvalid}
          <p class="m-0 w-full text-sm text-red-400" role="alert">{$t('wrapped.period.invalid')}</p>
        {/if}
      </form>
    {/if}
  </header>

  {#if status === 'loading' || status === 'computing'}
    <p class="m-0 text-muma-spotify-text animate-pulse" role="status">
      {$t(status === 'computing' ? 'wrapped.computing' : 'wrapped.loading')}
    </p>
  {:else if status === 'unavailable'}
    <div class="flex flex-col items-start gap-3" role="alert">
      <p class="m-0 text-muma-spotify-text">{$t('wrapped.unavailable')}</p>
      <button
        type="button"
        class="rounded-full bg-white text-black font-bold px-4 py-1.5 border-none cursor-pointer"
        onclick={() => (attempt += 1)}
      >{$t('wrapped.retry')}</button>
    </div>
  {:else if emptyUser}
    <section class="flex flex-col items-start gap-3 rounded-lg bg-muma-spotify-panel p-6" data-testid="wrapped-empty">
      <h2 class="m-0 text-2xl font-bold">{$t('wrapped.empty')}</h2>
      <p class="m-0 text-muma-spotify-text">{$t('wrapped.emptyHelp')}</p>
      <div class="flex flex-wrap gap-2">
        <button type="button" class="rounded-full bg-white text-black font-bold px-4 py-1.5 border-none cursor-pointer" onclick={() => onnavigate('listening')}>{$t('wrapped.openListening')}</button>
        <button type="button" class="rounded-full bg-muma-spotify-light text-white font-bold px-4 py-1.5 border-none cursor-pointer" onclick={() => onnavigate('settings')}>{$t('wrapped.openSettings')}</button>
      </div>
    </section>
  {:else}
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 snap-y snap-mandatory md:snap-none" data-testid="wrapped-cards">
      {#each cards as entry (entry.face.id)}
        {@const onshare = (face) => shareCard(face, entry.tint)}
        {#if entry.face.kind === 'hero'}
          <HeroCard face={entry.face} tint={entry.tint} {onshare} />
        {:else if entry.face.kind === 'rank'}
          <RankCard face={entry.face} tint={entry.tint} {onshare} onlink={openLink} onplay={playCard} />
        {:else if entry.face.kind === 'bars'}
          <BarsCard face={entry.face} tint={entry.tint} {onshare} />
        {:else if entry.face.kind === 'clock'}
          <ClockCard face={entry.face} tint={entry.tint} {onshare} />
        {:else if entry.face.kind === 'heatmap'}
          <HeatmapCard face={entry.face} tint={entry.tint} {onshare} />
        {:else}
          <FactCard face={entry.face} tint={entry.tint} {onshare} onlink={openLink} />
        {/if}
      {/each}
      {#if coverage}
        <CoverageCard model={coverage} />
      {/if}
    </div>
  {/if}
</div>
