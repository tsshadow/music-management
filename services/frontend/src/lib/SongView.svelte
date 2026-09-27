<script>
  import { seedFromTrack } from './entitySeeds.js';
  import { t } from './i18n/index.js';
  import TrackList from './TrackList.svelte';
  import { loadVersions as fetchVersions } from './versions.js';

  /**
   * One song and every file of it.
   *
   * The list is fetched by workId rather than derived from whatever list you came from:
   * the row you clicked is the one version the server chose, and the rest were collapsed
   * away before the browser saw them. Asking the server is also what makes the
   * alternatives playable -- muma's own version API answers with paths and muma ids, and
   * the player can use neither.
   */
  const { workId, onnavigate } = $props();

  let versions = $state([]);
  let isLoading = $state(true);
  let failed = $state(false);

  //: Which load is the current one. Navigating between two songs -- the back button does
  //: this -- leaves the first request in flight, and a slow answer would otherwise land
  //: under the next song's title. Every load claims a number and only writes if it still
  //: holds the latest.
  let loadToken = 0;

  //: Where following the server's pages stops regardless. A work holding more than this is
  //: not something this library has (the largest is 16) -- it is a grouping fault, not a
  //: song -- and fetching forever would hang the page rather than show the fault.
  const MAX_VERSIONS = 500;

  const canonical = $derived(
    versions.find((version) => version.isCanonical === true || version.isCanonical === 'true') ||
      versions[0] ||
      null,
  );

  $effect(() => {
    loadVersions(workId);
  });

  /**
   * Loads every version of one song and writes it into this page's own state.
   *
   * A thin wrapper around the shared `loadVersions` in `versions.js` -- increment F reused
   * that loop for the player's "other versions" section, so the paging and the "Subsonic's
   * failures are HTTP 200" check live there now. This page keeps only what is its own
   * concern: the loading/failure flags and the staleness guard against a slow answer landing
   * under the next song's title after the back button already moved on.
   *
   * @param {string|number} id - The work id.
   */
  async function loadVersions(id) {
    const token = ++loadToken;
    isLoading = true;
    failed = false;
    try {
      const result = await fetchVersions(id, { max: MAX_VERSIONS });
      if (token !== loadToken) return;
      versions = result;
    } catch (e) {
      if (token !== loadToken) return;
      console.error('Failed to load song versions:', e);
      failed = true;
      versions = [];
    } finally {
      if (token === loadToken) isLoading = false;
    }
  }
</script>

<div class="flex flex-col gap-6">
  {#if isLoading}
    <p class="text-muma-spotify-text">{$t('common.loading')}</p>
  {:else if failed}
    <p class="text-muma-spotify-text">{$t('track.versionsFailed')}</p>
  {:else if !canonical}
    <p class="text-muma-spotify-text">{$t('song.notFound')}</p>
  {:else}
    <header class="flex flex-col gap-2">
      <span class="text-xs uppercase tracking-wide text-muma-spotify-text">{$t('song.heading')}</span>
      <h2 class="text-3xl font-bold m-0 text-white">{canonical.title}</h2>
      <button
        class="self-start bg-transparent border-none p-0 text-muma-spotify-text hover:text-white hover:underline cursor-pointer"
        onclick={() => { if (canonical.artistId && onnavigate) { seedFromTrack(canonical); onnavigate(`artist:${canonical.artistId}`); } }}
      >
        {canonical.artist}
      </button>
      <p class="text-sm text-muma-spotify-text m-0">
        {versions.length === 1 ? $t('track.onlyVersion') : $t('song.versionCount', { count: versions.length })}
      </p>
    </header>

    <TrackList tracks={versions} {onnavigate} showDate={true} />
  {/if}
</div>
