<script>
  import { peekSeed, seedFromTrack } from './entitySeeds.js';
  import { entityCache, songVersionsKey } from './entityLoaders.js';
  import { t } from './i18n/index.js';
  import { authParams } from './store.js';
  import { coverArtSrc, localCoverArt } from './coverArt.js';
  import { offline } from './subsonic.js';
  import TrackList from './TrackList.svelte';
  import Skeleton from './loading/Skeleton.svelte';
  import SkeletonRows from './loading/SkeletonRows.svelte';
  import Throbber from './loading/Throbber.svelte';
  import { loadVersions as fetchVersions } from './versions.js';

  /**
   * One song and every file of it.
   *
   * The list is fetched by workId rather than derived from whatever list you came from:
   * the row you clicked is the one version the server chose, and the rest were collapsed
   * away before the browser saw them. Asking the server is also what makes the
   * alternatives playable -- muma's own version API answers with paths and muma ids, and
   * the player can use neither.
   *
   * The page opens at once (issue #111, docs/designs/perceived-performance/): the header comes
   * from the row that was tapped (its title, artist and cover, left by `openSong`), skeleton rows
   * stand where the versions go, and each page of versions is drawn as it lands rather than after
   * the last of up to five pages. The server's canonical replaces the seed as soon as it is seen.
   */
  const { workId, onnavigate } = $props();

  let versions = $state([]);
  let isLoading = $state(true);
  let failed = $state(false);
  /** What the tapped row knew; stands in for the canonical until the server names one. */
  let seed = $state(null);

  //: Which load is the current one. Navigating between two songs -- the back button does
  //: this -- leaves the first request in flight, and a slow answer would otherwise land
  //: under the next song's title. Every load claims a number and only writes if it still
  //: holds the latest.
  let loadToken = 0;

  //: Where following the server's pages stops regardless. A work holding more than this is
  //: not something this library has (the largest is 16) -- it is a grouping fault, not a
  //: song -- and fetching forever would hang the page rather than show the fault.
  const MAX_VERSIONS = 500;

  /** The version the server marked canonical, once a page carrying it has landed. */
  const canonicalSeen = $derived(
    versions.find((version) => version.isCanonical === true || version.isCanonical === 'true') ??
      null,
  );

  /**
   * What heads the page. The canonical when the server has named it; while pages are still
   * coming, the tapped row (usually that very canonical) rather than whichever version happens
   * to be first; once everything is in without a canonical, the first version.
   */
  const canonical = $derived(
    canonicalSeen ??
      (isLoading && seed
        ? { title: seed.name, artist: seed.artist, artistId: seed.artistId, coverArt: seed.coverArt }
        : (versions[0] ?? null)),
  );

  $effect(() => {
    loadVersions(workId);
  });

  /**
   * Loads every version of one song and writes it into this page's own state, page by page.
   *
   * A thin wrapper around the shared `loadVersions` in `versions.js`, which owns the paging and
   * the "Subsonic's failures are HTTP 200" check. This page keeps what is its own concern: the
   * seed, the loading/failure flags, a revisit answered from the entity cache, and the staleness
   * guard against a slow answer landing under the next song's title after the back button
   * already moved on.
   *
   * @param {string|number} id - The work id.
   * @param {{force?: boolean}} [options] - `force` skips the cache (the retry button).
   */
  async function loadVersions(id, { force = false } = {}) {
    const token = ++loadToken;
    const key = songVersionsKey(id);
    const cached = force ? null : entityCache.peek(key);
    seed = peekSeed('song', id);
    failed = false;
    if (cached) {
      // A revisit: the list at once, and a quiet refresh only when it has gone stale.
      versions = cached.value;
      isLoading = false;
      if (cached.fresh) return;
    } else {
      versions = [];
      isLoading = true;
    }
    try {
      const result = await fetchVersions(id, {
        max: MAX_VERSIONS,
        // A refresh keeps the cached list on screen until the whole answer is in.
        onPage: cached
          ? undefined
          : (soFar) => {
              if (token === loadToken) versions = soFar;
            },
      });
      if (token !== loadToken) return;
      versions = result;
      entityCache.set(key, result);
    } catch (e) {
      if (token !== loadToken) return;
      console.error('Failed to load song versions:', e);
      // A refresh that failed leaves the cached list alone; a first load says it failed and
      // keeps whatever pages had already arrived.
      if (!cached) failed = true;
    } finally {
      if (token === loadToken) isLoading = false;
    }
  }

  /** The error line's "Opnieuw". */
  function retry() {
    loadVersions(workId, { force: true });
  }
</script>

<div class="flex flex-col gap-6">
  <header class="flex items-end gap-4 md:gap-6" data-testid="song-header">
    {#if canonical?.coverArt}
      <img
        src={coverArtSrc(canonical.coverArt, 300, $authParams, $localCoverArt, $offline)}
        alt=""
        class="w-28 h-28 md:w-40 md:h-40 shrink-0 rounded-md object-cover shadow-lg shadow-black/50"
        data-testid="song-cover"
      />
    {:else if isLoading}
      <Skeleton class="w-28 h-28 md:w-40 md:h-40 shrink-0 rounded-md" />
    {/if}
    <div class="flex flex-col gap-2 min-w-0">
      <span class="text-xs uppercase tracking-wide text-muma-spotify-text">{$t('song.heading')}</span>
      {#if canonical?.title}
        <h2 class="text-3xl font-bold m-0 text-white">{canonical.title}</h2>
      {:else if isLoading}
        <div class="w-64 md:w-96 max-w-full" data-testid="song-title-skeleton"><Skeleton class="h-8 w-full" /></div>
      {/if}
      {#if canonical?.artist}
        <button
          class="self-start bg-transparent border-none p-0 text-muma-spotify-text hover:text-white hover:underline cursor-pointer text-left"
          onclick={() => { if (canonical.artistId && onnavigate) { seedFromTrack(canonical); onnavigate(`artist:${canonical.artistId}`); } }}
        >
          {canonical.artist}
        </button>
      {:else if isLoading}
        <Skeleton class="h-4 w-32" />
      {/if}
      {#if !isLoading && !failed && versions.length > 0}
        <p class="text-sm text-muma-spotify-text m-0">
          {versions.length === 1 ? $t('track.onlyVersion') : $t('song.versionCount', { count: versions.length })}
        </p>
      {:else if isLoading && versions.length > 0}
        <p class="text-sm text-muma-spotify-text m-0 flex items-center gap-2">
          {$t('song.versionCount', { count: versions.length })}
          <Throbber size={14} />
        </p>
      {/if}
    </div>
  </header>

  {#if versions.length > 0}
    <TrackList tracks={versions} {onnavigate} showDate={true} />
  {/if}

  {#if isLoading}
    <!-- The first page's rows, or the pages still to come under the ones already drawn. -->
    <SkeletonRows count={versions.length > 0 ? 3 : 6} />
  {:else if failed}
    <!-- Styleguide, Loading States: a section error is one muted line and the "Opnieuw" pill. -->
    <div class="flex flex-col items-center gap-3 py-6 text-center" role="alert" data-testid="section-error">
      <p class="text-sm text-muma-spotify-muted m-0">{$t('track.versionsFailed')}</p>
      <button
        class="bg-transparent border border-muma-spotify-muted text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]"
        onclick={retry}
      >{$t('common.retry')}</button>
    </div>
  {:else if versions.length === 0}
    <p class="text-muma-spotify-text">{$t('song.notFound')}</p>
  {/if}
</div>
