<script>
  import { t } from './i18n/index.js';
  import { authParams } from './store.js';
  import TrackList from './TrackList.svelte';

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

  //: One page of versions. A work holding more than this is not something this library
  //: has (the largest is 16), but a silent truncation is invisible afterwards, so the
  //: loader follows the server's moreResults instead of assuming one page is all of it.
  const PAGE_SIZE = 100;

  //: Where following those pages stops regardless. A work this large is a grouping fault,
  //: not a song, and fetching forever would hang the page rather than show the fault.
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
   * Loads every version of one song.
   *
   * @param {string|number} id - The work id.
   */
  async function loadVersions(id) {
    const token = ++loadToken;
    isLoading = true;
    failed = false;
    const collected = [];
    let offset = 0;
    try {
      while (collected.length < MAX_VERSIONS) {
        const response = await fetch(
          `/rest/getSpotifyTracks?workId=${id}&count=${PAGE_SIZE}&offset=${offset}&${$authParams}`,
        );
        const data = await response.json();
        // Subsonic answers its own failures with HTTP 200 and an error in the body, so the
        // status in the body is the only thing that says this worked.
        const payload = data?.['subsonic-response'];
        if (!response.ok || payload?.status !== 'ok') {
          throw new Error(payload?.error?.message || response.statusText || 'failed');
        }
        const result = payload.tracks?.track || [];
        collected.push(...(Array.isArray(result) ? result : [result]));

        const more = payload.tracks?.moreResults;
        if (!(more === true || more === 'true') || result.length === 0) break;
        offset = Number(payload.tracks?.nextOffset ?? offset + PAGE_SIZE);
      }
      if (token !== loadToken) return;
      versions = collected;
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
    <p class="text-[#b3b3b3]">{$t('common.loading')}</p>
  {:else if failed}
    <p class="text-[#b3b3b3]">{$t('track.versionsFailed')}</p>
  {:else if !canonical}
    <p class="text-[#b3b3b3]">{$t('song.notFound')}</p>
  {:else}
    <header class="flex flex-col gap-2">
      <span class="text-xs uppercase tracking-wide text-[#b3b3b3]">{$t('song.heading')}</span>
      <h2 class="text-3xl font-bold m-0 text-white">{canonical.title}</h2>
      <button
        class="self-start bg-transparent border-none p-0 text-[#b3b3b3] hover:text-white hover:underline cursor-pointer"
        onclick={() => canonical.artistId && onnavigate && onnavigate(`artist:${canonical.artistId}`)}
      >
        {canonical.artist}
      </button>
      <p class="text-sm text-[#b3b3b3] m-0">
        {versions.length === 1 ? $t('track.onlyVersion') : $t('song.versionCount', { count: versions.length })}
      </p>
    </header>

    <TrackList tracks={versions} {onnavigate} showDate={true} />
  {/if}
</div>
