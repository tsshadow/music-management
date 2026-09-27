<script>
  /**
   * The artist or album page as far as the link that opened it knows it, shown while the page's
   * own chunk is on its way (issue #118).
   *
   * `ArtistView` and `AlbumView` are lazily loaded, but the optimistic navigation of #107 promises
   * the heading at once: this is the tiny, always-loaded stand-in that keeps that promise. It draws
   * the same header -- picture, kind line, name -- from the seed (`entitySeeds.js`) with the same
   * classes, and skeleton rows below, so when the real page replaces it nothing moves but the
   * rows filling in. Without a seed it is the same skeleton header the page shows itself.
   *
   * @property {'artist'|'album'} kind
   * @property {string} id
   */
  import { t } from './i18n/index.js';
  import { authParams, restUrl } from './store.js';
  import { getArtistImageUrl } from './utils.js';
  import { peekSeed } from './entitySeeds.js';
  import Skeleton from './loading/Skeleton.svelte';
  import SkeletonRows from './loading/SkeletonRows.svelte';

  const { kind, id } = $props();

  const seed = $derived(peekSeed(kind, id));
  const artist = $derived(kind === 'artist');
  const cover = $derived(
    artist
      ? seed ? getArtistImageUrl({ ...seed, id }, $authParams) : null
      : seed?.coverArt ? restUrl(`/rest/getCoverArt?id=${seed.coverArt}&size=300&${$authParams}`) : null,
  );
</script>

<div class="flex flex-col" data-testid="entity-page-shell">
  <header class="h-auto md:h-[340px] flex flex-col md:flex-row items-center md:items-end p-6 md:p-8 bg-linear-to-b from-transparent to-black/50 relative gap-6 text-center md:text-left">
    <div class="w-[160px] h-[160px] md:w-[232px] md:h-[232px] flex-shrink-0">
      {#if seed}
        <img
          src={cover ?? (artist ? '/images/unknown-artist.svg' : '/images/spotify-fallback.svg')}
          alt={seed.name ?? ''}
          class="w-full h-full object-cover shadow-[0_4px_60px_rgba(0,0,0,0.5)] {artist ? 'rounded-full' : ''}"
          onerror={(e) => (e.target.src = artist ? '/images/unknown-artist.svg' : '/images/spotify-fallback.svg')}
        />
      {:else}
        <Skeleton class="w-full h-full {artist ? 'rounded-full' : ''}" />
      {/if}
    </div>
    <div class="flex flex-col min-w-0">
      {#if artist}
        <div class="flex items-center justify-center md:justify-start gap-2 text-sm font-bold mb-2">
          <svg viewBox="0 0 24 24" width="24" height="24" fill="#3d91f4" aria-hidden="true">
            <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zM10 17l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"></path>
          </svg>
          {$t('artist.verified')}
        </div>
      {:else}
        <div class="uppercase text-xs font-bold">{$t('common.album')}</div>
      {/if}
      {#if seed?.name}
        <h1 class="{artist ? 'text-4xl md:text-7xl lg:text-9xl m-0' : 'text-3xl md:text-5xl lg:text-7xl my-2'} font-black leading-tight md:leading-none">{seed.name}</h1>
      {:else}
        <div class="w-64 md:w-[28rem] max-w-full"><Skeleton class="h-10 md:h-20 w-full" /></div>
      {/if}
      <div class="flex items-center justify-center md:justify-start gap-4 mt-6" aria-hidden="true">
        <Skeleton class="w-12 h-12 md:w-14 md:h-14 rounded-full" />
        <Skeleton class="w-10 h-10 md:w-12 md:h-12 rounded-full" />
      </div>
    </div>
  </header>
  <div class="p-6 md:p-8">
    <SkeletonRows count={8} />
  </div>
</div>
