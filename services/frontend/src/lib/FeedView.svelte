<script>
  import { t } from './i18n/index.js';
  import { authParams, currentTrack, playerState } from './store.js';
  import { loadFeedDetail, loadFeedPage, RELEASE_RADAR } from './feeds.js';
  import TrackList from './TrackList.svelte';
  import { startQueue } from './queue.js';

  /**
   * One personalized feed, whole: everything MuMa picked, in its order, with a play button.
   *
   * The home rows show the head of the same list. This is where the rest of it lives, and where
   * "start the daily mix" is one click rather than a scroll. At the end of the list "Meer laden"
   * appends the next page of the same day's feed (docs/designs/feed-length/), and a queue started
   * here carries that continuation so the player tops it up on its own.
   */
  const { slug = RELEASE_RADAR, onnavigate } = $props();

  let tracks = $state([]);
  let isLoading = $state(true);
  // Server-supplied title/subtitle and hardness numbers, once the feed's own page answers.
  // Falling back to the old fixed radar/mix copy keeps release-radar and daily-mix readable even
  // when the request failed and MuMa never got to say anything.
  let detail = $state(null);
  // Where the feed continues (`next_offset`), null once MuMa says there is nothing more.
  let nextOffset = $state(null);
  let loadingMore = $state(false);

  const isRadar = $derived(slug === RELEASE_RADAR);
  const title = $derived(detail?.title ?? (isRadar ? $t('nav.releaseRadar') : $t('nav.dailyMix')));
  const subtitle = $derived(detail?.subtitle ?? (isRadar ? $t('feed.radarSubtitle') : $t('feed.mixSubtitle')));

  /**
   * "band ≤42 hardheid · 3 aangevuld" -- shown only for the three spectrum mixes, which are the
   * only policies `hardness_band` is ever set for.
   */
  const bandLine = $derived.by(() => {
    if (!detail?.hardnessBand) return null;
    const [lo, hi] = detail.hardnessBand;
    const parts = [$t('feed.bandRange', { lo: Math.round(lo), hi: Math.round(hi) })];
    if (detail.filledFromUnknown) parts.push($t('feed.filledFromUnknown', { count: detail.filledFromUnknown }));
    return parts.join(' · ');
  });

  $effect(() => {
    const auth = $authParams;
    const which = slug;
    if (!auth) return;

    isLoading = true;
    tracks = [];
    detail = null;
    nextOffset = null;
    loadFeedDetail(which, auth)
      .then((result) => {
        // The feed may have changed while this was in flight -- a click on the other one in the
        // sidebar restarts this effect -- so only the answer to the current question is kept.
        if (which === slug) {
          tracks = result.tracks;
          detail = result;
          nextOffset = result.nextOffset ?? null;
        }
      })
      .finally(() => {
        if (which === slug) isLoading = false;
      });
  });

  /**
   * "Meer laden": appends the feed's next page, leaving out any song the list already shows. A
   * failed request keeps the button so a second tap can try again; a page that says there is
   * no more removes it.
   */
  async function loadMore() {
    const auth = $authParams;
    const which = slug;
    if (loadingMore || !nextOffset || !auth) return;
    loadingMore = true;
    try {
      const page = await loadFeedPage(which, auth, nextOffset);
      if (which !== slug || page.failed) return;
      const have = new Set(tracks.map((track) => String(track.id)));
      tracks = [...tracks, ...page.tracks.filter((track) => !have.has(String(track.id)))];
      nextOffset = page.nextOffset;
    } finally {
      loadingMore = false;
    }
  }

  /** Queues the whole feed, in MuMa's order, and starts it; the queue continues the feed. */
  function playAll() {
    if (tracks.length === 0) return;
    startQueue(tracks, { name: title, continuation: { slug, nextOffset } });
    currentTrack.set(tracks[0]);
    playerState.update((s) => ({ ...s, playing: true }));
  }
</script>

<div class="flex flex-col gap-8 pb-12">
  <header class="flex flex-col md:flex-row items-center md:items-end gap-6 mb-4 text-center md:text-left">
    <div class="w-40 h-40 md:w-52 md:h-52 bg-linear-to-br from-indigo-700 to-indigo-900 shadow-2xl flex items-center justify-center flex-shrink-0">
      <svg viewBox="0 0 24 24" width="80" height="80" fill="white">
        {#if isRadar}
          <path d="M12 2a10 10 0 1 0 10 10h-2a8 8 0 1 1-8-8V2zm0 4a6 6 0 1 0 6 6h-2a4 4 0 1 1-4-4V6zm0 4a2 2 0 1 0 2 2 2 2 0 0 0-2-2z"></path>
        {:else}
          <path d="M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z"></path>
        {/if}
      </svg>
    </div>
    <div class="flex-1">
      <div class="text-xs font-bold uppercase tracking-wider mb-2">{$t('common.playlist')}</div>
      <h1 class="text-4xl md:text-7xl lg:text-8xl font-black mb-6">{title}</h1>
      <div class="flex items-center gap-2 text-sm font-medium">
        <span class="text-white">{subtitle}</span>
        {#if tracks.length > 0}
          <span class="text-muma-spotify-text">• {$t('common.trackCount', { count: tracks.length })}</span>
        {/if}
      </div>
      {#if bandLine}
        <div class="text-xs text-muma-spotify-text mt-1">{bandLine}</div>
      {/if}
    </div>
  </header>

  <div class="px-2">
    <div class="flex items-center gap-8 mb-8">
      {#if tracks.length > 0}
        <button
          class="bg-brand text-black w-14 h-14 rounded-full flex items-center justify-center shadow-xl hover:scale-105 active:scale-95 transition cursor-pointer border-none"
          onclick={playAll}
          title={$t('common.playAll')}
        >
          <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
            <path d="M7 6v12l10-6z"></path>
          </svg>
        </button>
      {/if}
    </div>

    {#if isLoading}
      <div class="text-muma-spotify-text p-12 text-center">{$t('common.loading')}</div>
    {:else if tracks.length === 0}
      <div class="text-muma-spotify-text p-12 text-center">
        <p class="mb-2">{$t('feed.empty')}</p>
        <p class="text-sm">{isRadar ? $t('feed.emptyRadarHelp') : $t('feed.emptyMixHelp')}</p>
      </div>
    {:else}
      <TrackList {tracks} onnavigate={onnavigate} />
      {#if nextOffset}
        <!-- The existing "load more" pattern (docs/styleguide.md, Components): the outlined pill
             under a track list, the same one the song and artist lists use. -->
        <div class="flex justify-center py-6">
          <button
            class="bg-transparent border border-muma-spotify-muted text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04] disabled:cursor-default"
            onclick={loadMore}
            disabled={loadingMore}
          >
            {loadingMore ? $t('common.loading') : $t('common.loadMore')}
          </button>
        </div>
      {/if}
    {/if}
  </div>
</div>
