<script>
  import { untrack } from 'svelte';
  import { t } from './i18n/index.js';
  import { authParams, currentTrack, playerState } from './store.js';
  import {
    DAILY_MIX,
    RELEASE_RADAR,
    loadFeedDetail,
    loadFeedPage,
    resolveFeedChunk,
    streamFeedDetail,
  } from './feeds.js';
  import { peekSeed } from './entitySeeds.js';
  import { entityCache, feedKey } from './entityLoaders.js';
  import TrackList from './TrackList.svelte';
  import ListEnd from './ListEnd.svelte';
  import Skeleton from './loading/Skeleton.svelte';
  import SkeletonRows from './loading/SkeletonRows.svelte';
  import SectionState from './loading/SectionState.svelte';
  import Throbber from './loading/Throbber.svelte';
  import { startQueue } from './queue.js';
  import { feedContinuation } from './feedQueue.js';

  /**
   * One personalized feed, whole: everything MuMa picked, in its order, with a play button.
   *
   * The home rows show the head of the same list. This is where the rest of it lives, and where
   * "start the daily mix" is one click rather than a scroll. At the end of the list "Meer laden"
   * appends the next page of the same day's feed (docs/designs/feed-length/), and a queue started
   * here carries that continuation so the player tops it up on its own.
   *
   * It loads progressively (issue #110, docs/designs/perceived-performance/): the header is drawn
   * at once from what the tapped card knew (or the fixed radar/mix copy), skeleton rows stand
   * where the tracks go, and MuMa's paths are resolved against LMS in parallel chunks whose rows
   * appear as they land -- in MuMa's order, never in arrival order. A chunk LMS failed to answer
   * gets its own retry; a revisit within a few minutes is answered from the entity cache.
   */
  const { slug = RELEASE_RADAR, onnavigate } = $props();

  /**
   * One `getSongsByPath` chunk of the feed's first page. `missing` is how many of its paths LMS
   * had no song for, once it answered. A cached page is one chunk without paths.
   *
   * @typedef {{paths: string[]|null, status: 'loading'|'ready'|'error', songs: Object[], missing: number}} Chunk
   */

  // Server-supplied title/subtitle and hardness numbers, once the feed's own page answers.
  let detail = $state(null);
  /** @type {'loading'|'ready'|'error'} Whether MuMa's answer for the feed itself is in. */
  let headerStatus = $state('loading');
  /** @type {Chunk[]} */
  let chunks = $state([]);
  /** What the card that opened this page knew: its title and subtitle. */
  let seed = $state(null);
  // Tracks "Meer laden" appended after the first page, and what LMS lacked of them.
  let more = $state([]);
  let moreUnresolved = $state(0);
  // Where the feed continues (`next_offset`), null once MuMa says there is nothing more.
  let nextOffset = $state(null);
  let loadingMore = $state(false);
  // Whether "Meer laden" fetched anything here, so a feed that ran out says so ("Einde van de
  // lijst") while one that fit on its first page ends in nothing.
  let pagedMore = $state(false);
  /** Play pressed before the first page was in: started as soon as it is. */
  let pendingPlay = $state(false);
  // Which load is current; an answer for a feed the listener already left is dropped.
  let loadSeq = 0;

  /** Every chunk of the first page has answered, one way or the other. */
  const headSettled = $derived(
    headerStatus !== 'loading' && chunks.every((chunk) => chunk.status !== 'loading'),
  );
  /**
   * The first page's songs in MuMa's order: every answered chunk up to the first one still on
   * its way, so a second chunk landing early never appears above the first. A failed chunk is
   * skipped -- its retry sits under the list -- rather than holding back the ones after it.
   */
  const headTracks = $derived.by(() => {
    const out = [];
    for (const chunk of chunks) {
      if (chunk.status === 'loading') break;
      if (chunk.status === 'ready') out.push(...chunk.songs);
    }
    return out;
  });
  const tracks = $derived(headSettled ? [...headTracks, ...more] : headTracks);
  /** How many paths are still being resolved, to size the skeleton under the rows. */
  const pendingPaths = $derived(
    chunks.reduce((sum, chunk) => (chunk.status === 'loading' ? sum + (chunk.paths?.length ?? 0) : sum), 0),
  );
  const hasFailedChunk = $derived(chunks.some((chunk) => chunk.status === 'error'));
  // MuMa's rows that LMS had no song for, over every page shown so far (bug report 122). The list
  // leaves them out -- they cannot be played -- and the header says how many, so a 100-track page
  // showing 98 is explained rather than looking like a bug.
  const unresolved = $derived(
    chunks.reduce((sum, chunk) => (chunk.status === 'ready' ? sum + chunk.missing : sum), 0) +
      moreUnresolved,
  );
  // What a tapped row or the play button hands the queue, so either way it continues the feed.
  // Not before the first page is whole: a queue of half of it that continued at `nextOffset`
  // would skip the half still loading.
  const continuation = $derived(headSettled ? feedContinuation(slug, nextOffset) : null);

  const isRadar = $derived(slug === RELEASE_RADAR);
  /** The fixed copy for the two feeds that had a page before MuMa named its feeds. */
  const fixedTitle = $derived(
    isRadar ? $t('nav.releaseRadar') : slug === DAILY_MIX ? $t('nav.dailyMix') : null,
  );
  const fixedSubtitle = $derived(
    isRadar ? $t('feed.radarSubtitle') : slug === DAILY_MIX ? $t('feed.mixSubtitle') : null,
  );
  // Null while nothing is known yet: the header draws a skeleton bar instead of a guess.
  const title = $derived(
    detail?.title ??
      seed?.name ??
      fixedTitle ??
      (headerStatus === 'loading' ? null : $t('nav.dailyMix')),
  );
  const subtitle = $derived(
    detail?.subtitle ??
      fixedSubtitle ??
      seed?.subtitle ??
      (headerStatus === 'loading' ? null : $t('feed.mixSubtitle')),
  );

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
    untrack(() => load(which, auth));
  });

  // Play pressed while the first page was loading: start it the moment it is whole.
  $effect(() => {
    if (!pendingPlay || !headSettled) return;
    untrack(() => {
      pendingPlay = false;
      playAll();
    });
  });

  /**
   * Shows a whole, already resolved first page (a cached one, or a background refresh).
   *
   * @param {Awaited<ReturnType<typeof loadFeedDetail>>} result
   */
  function showResult(result) {
    detail = result;
    headerStatus = result.state === 'error' ? 'error' : 'ready';
    nextOffset = result.nextOffset ?? null;
    chunks = [{ paths: null, status: 'ready', songs: result.tracks, missing: result.unresolved ?? 0 }];
  }

  /** Whether a first page is worth caching: MuMa answered and every chunk resolved. */
  function isWhole(result) {
    return result.state !== 'error' && !result.failedChunks;
  }

  /**
   * Starts the feed's first page: from the cache when it has one (refreshed in the background
   * once stale, and only swapped in while the listener has not paged further), otherwise
   * streamed -- the header as soon as MuMa answers, each chunk's rows as LMS resolves it.
   *
   * @param {string} which
   * @param {string} auth
   * @param {{force?: boolean}} [options] - `force` skips the cache (the retry button).
   */
  function load(which, auth, { force = false } = {}) {
    const seq = ++loadSeq;
    const key = feedKey(which);
    seed = peekSeed('feed', which);
    more = [];
    moreUnresolved = 0;
    pagedMore = false;
    pendingPlay = false;

    const cached = force ? null : entityCache.peek(key);
    if (cached) {
      showResult(cached.value);
      if (cached.fresh) return;
      loadFeedDetail(which, auth).then((result) => {
        if (seq !== loadSeq || pagedMore || !isWhole(result)) return;
        entityCache.set(key, result);
        showResult(result);
      });
      return;
    }

    detail = null;
    headerStatus = 'loading';
    chunks = [];
    nextOffset = null;
    streamFeedDetail(which, auth, {
      onHeader: (header) => {
        if (seq !== loadSeq) return;
        detail = header;
        nextOffset = header.nextOffset ?? null;
        headerStatus = header.state === 'error' ? 'error' : 'ready';
        chunks = header.chunks.map((paths) => ({ paths, status: 'loading', songs: [], missing: 0 }));
      },
      onChunk: (index, result) => {
        if (seq === loadSeq) settleChunk(index, result);
      },
    }).then((result) => {
      if (seq === loadSeq && isWhole(result)) entityCache.set(key, result);
    });
  }

  /**
   * Records one chunk's answer from LMS.
   *
   * @param {number} index
   * @param {{songs: Object[], failed: boolean}} result
   */
  function settleChunk(index, result) {
    chunks = chunks.map((chunk, i) =>
      i !== index
        ? chunk
        : {
            ...chunk,
            status: result.failed ? 'error' : 'ready',
            songs: result.failed ? [] : result.songs,
            missing: result.failed ? 0 : Math.max(0, (chunk.paths?.length ?? 0) - result.songs.length),
          },
    );
  }

  /** The feed itself could not be loaded: ask MuMa again, from scratch. */
  function retryFeed() {
    const auth = $authParams;
    if (auth) load(slug, auth, { force: true });
  }

  /**
   * Asks LMS again for the chunks it failed to answer; the rows already shown stay. Once every
   * chunk has resolved, the page is whole and goes into the cache like a first try would have.
   */
  async function retryChunks() {
    const auth = $authParams;
    const seq = loadSeq;
    const which = slug;
    if (!auth) return;
    const failedIndexes = chunks.flatMap((chunk, i) => (chunk.status === 'error' ? [i] : []));
    chunks = chunks.map((chunk) => (chunk.status === 'error' ? { ...chunk, status: 'loading' } : chunk));
    await Promise.all(
      failedIndexes.map(async (index) => {
        const result = await resolveFeedChunk(chunks[index].paths ?? [], auth);
        if (seq === loadSeq) settleChunk(index, result);
      }),
    );
    if (seq !== loadSeq || chunks.some((chunk) => chunk.status !== 'ready')) return;
    entityCache.set(
      feedKey(which),
      $state.snapshot({ ...detail, tracks: headTracks, unresolved, failedChunks: 0 }),
    );
  }

  /**
   * "Meer laden": appends the feed's next page, leaving out any song the list already shows. A
   * failed request keeps the button so a second tap can try again; a page that says there is
   * no more removes it.
   */
  async function loadMore() {
    const auth = $authParams;
    const which = slug;
    const seq = loadSeq;
    if (loadingMore || !nextOffset || !auth) return;
    loadingMore = true;
    try {
      const page = await loadFeedPage(which, auth, nextOffset);
      if (seq !== loadSeq || page.failed) return;
      const have = new Set(tracks.map((track) => String(track.id)));
      more = [...more, ...page.tracks.filter((track) => !have.has(String(track.id)))];
      nextOffset = page.nextOffset;
      pagedMore = true;
      moreUnresolved += page.unresolved ?? 0;
    } finally {
      loadingMore = false;
    }
  }

  /** Queues the whole feed, in MuMa's order, and starts it; the queue continues the feed. */
  function playAll() {
    if (tracks.length === 0) return;
    startQueue(tracks, { name: title, continuation });
    currentTrack.set(tracks[0]);
    playerState.update((s) => ({ ...s, playing: true }));
  }

  /** The play button: at once when the page is whole, as soon as it is otherwise. */
  function pressPlay() {
    if (headSettled) playAll();
    else pendingPlay = true;
  }
</script>

<div class="flex flex-col gap-8 pb-12">
  <header class="flex flex-col md:flex-row items-center md:items-end gap-6 mb-4 text-center md:text-left" data-testid="feed-header">
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
      {#if title}
        <h1 class="text-4xl md:text-7xl lg:text-8xl font-black mb-6">{title}</h1>
      {:else}
        <div class="mb-6 flex justify-center md:justify-start" data-testid="feed-title-skeleton">
          <Skeleton class="h-10 md:h-[4.5rem] lg:h-24 w-64 md:w-[28rem] max-w-full" />
        </div>
      {/if}
      <div class="flex items-center gap-2 text-sm font-medium">
        {#if subtitle}
          <span class="text-white">{subtitle}</span>
        {:else}
          <Skeleton class="h-4 w-40" />
        {/if}
        {#if tracks.length > 0}
          <span class="text-muma-spotify-text">• {$t('common.trackCount', { count: tracks.length })}</span>
        {/if}
        {#if unresolved > 0}
          <span class="text-muma-spotify-text" data-testid="feed-unresolved">• {$t('feed.unresolved', { count: unresolved })}</span>
        {/if}
      </div>
      {#if bandLine}
        <div class="text-xs text-muma-spotify-text mt-1">{bandLine}</div>
      {/if}
    </div>
  </header>

  <div class="px-2">
    <div class="flex items-center gap-8 mb-8">
      {#if tracks.length > 0 || (!headSettled && headerStatus !== 'error')}
        <button
          class="bg-brand text-black w-14 h-14 rounded-full flex items-center justify-center shadow-xl hover:scale-105 active:scale-95 transition cursor-pointer border-none"
          onclick={pressPlay}
          title={$t('common.playAll')}
          data-testid="feed-play"
        >
          {#if pendingPlay}
            <Throbber size={24} />
          {:else}
            <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
              <path d="M7 6v12l10-6z"></path>
            </svg>
          {/if}
        </button>
      {/if}
    </div>

    {#if headerStatus === 'error'}
      <SectionState status="error" onretry={retryFeed} />
    {:else if headerStatus === 'loading'}
      <SkeletonRows count={8} />
    {:else if tracks.length === 0 && pendingPaths === 0 && !hasFailedChunk}
      <div class="text-muma-spotify-text p-12 text-center">
        <p class="mb-2">{$t('feed.empty')}</p>
        <p class="text-sm">{isRadar ? $t('feed.emptyRadarHelp') : $t('feed.emptyMixHelp')}</p>
      </div>
    {:else}
      {#if tracks.length > 0}
        <TrackList {tracks} {continuation} sourceName={title} onnavigate={onnavigate} />
      {/if}
      {#if pendingPaths > 0}
        <SkeletonRows count={Math.min(8, pendingPaths)} />
      {/if}
      {#if hasFailedChunk && pendingPaths === 0}
        <SectionState status="error" onretry={retryChunks} />
      {/if}
      {#if headSettled}
        <!-- The existing "load more" pattern (docs/styleguide.md, Components): the outlined pill
             under a track list, the same one the song and artist lists and the queue use. -->
        <ListEnd hasMore={Boolean(nextOffset)} ended={pagedMore} loading={loadingMore} onmore={loadMore} testid="feed-load-more" />
      {/if}
    {/if}
  </div>
</div>
