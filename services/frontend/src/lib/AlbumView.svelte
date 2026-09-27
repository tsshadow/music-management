<script>
  import { t, locale } from './i18n/index.js';
  import { untrack } from 'svelte';
  import { authParams, viewMode, currentTrack, playerState, restUrl } from './store.js';
  import TrackList from './TrackList.svelte';
  import ArtistList from './ArtistList.svelte';
  import { peekSeed } from './entitySeeds.js';
  import { albumInfoKey, albumKey, entityCache, fetchAlbum, fetchAlbumInfo } from './entityLoaders.js';
  import Skeleton from './loading/Skeleton.svelte';
  import SkeletonRows from './loading/SkeletonRows.svelte';
  import SectionState from './loading/SectionState.svelte';
  import Throbber from './loading/Throbber.svelte';
  import { recordPlace } from './recentPlaces.js';
  import { startQueue } from './queue.js';

  const { albumId, onnavigate } = $props();

  let album = $state(null);
  let allTracks = $state([]);
  let albumInfo = $state(null);
  /** What the link that opened this page knew; replaced by `album` as soon as that arrives. */
  let seed = $state(null);
  /** @type {'loading'|'ready'|'error'} */
  let albumStatus = $state('loading');
  /** Play or shuffle pressed before the tracks arrived: started as soon as they do. */
  let pendingPlay = $state(null);
  // Which load is current; an answer for an album the listener already left is dropped.
  let loadSeq = 0;

  /** The header: the server's album, or the seed standing in for it. */
  const display = $derived(album ?? (seed ? { ...seed, id: albumId } : null));

  /**
   * Toggles the starred status of the album.
   */
  async function toggleStar() {
    if (!album) return;
    const isCurrentlyStarred = !!album.starred;
    const endpoint = isCurrentlyStarred ? 'unstar' : 'star';

    // Optimistic update, mirrored into the cache so a revisit shows it too.
    setStarred(isCurrentlyStarred ? undefined : new Date().toISOString());

    try {
      const response = await fetch(restUrl(`/rest/${endpoint}?albumId=${albumId}&${$authParams}`));
      if (!response.ok) throw new Error('Failed to toggle star');
    } catch (e) {
      console.error(e);
      // Rollback
      setStarred(isCurrentlyStarred ? new Date().toISOString() : undefined);
    }
  }

  /**
   * Writes the star state to the page and to the cached album.
   *
   * @param {string|undefined} starred
   */
  function setStarred(starred) {
    const apply = (value) => {
      const next = { ...value };
      if (starred) next.starred = starred;
      else delete next.starred;
      return next;
    };
    album = apply(album);
    entityCache.update(albumKey(albumId), (cached) => ({ ...cached, album: apply(cached.album) }));
  }

  /**
   * Filtered tracks based on viewMode (songs vs sets), grouped by disc.
   */
  const groupedTracks = $derived.by(() => {
    let filtered;
    if ($viewMode === 'sets') {
      filtered = allTracks.filter(t => t.duration >= 600);
    } else {
      filtered = allTracks.filter(t => t.duration < 600);
    }

    const groups = {};
    filtered.forEach(t => {
      const disc = t.discNumber || 1;
      if (!groups[disc]) groups[disc] = [];
      groups[disc].push(t);
    });

    return Object.entries(groups).sort(([a], [b]) => Number(a) - Number(b));
  });

  const hasMultipleDiscs = $derived(groupedTracks.length > 1);

  /**
   * Helper to get disc title if available.
   * @param {number} discNumber
   */
  function getDiscTitle(discNumber) {
    if (album && album.discTitles) {
      const titles = Array.isArray(album.discTitles) ? album.discTitles : [album.discTitles];
      const found = titles.find(t => Number(t.disc) === Number(discNumber));
      if (found) return found.title;
    }
    return `Disc ${discNumber}`;
  }

  /**
   * Loads the album and, in parallel, its notes. Both go through the entity cache: a revisit
   * renders at once and refreshes in the background, and a press on the tile that opened this
   * page may already have started the album request (docs/designs/perceived-performance/).
   */
  function loadAlbum() {
    if (!$authParams) return;
    const seq = ++loadSeq;
    const id = albumId;
    // Nothing of the previous album survives into this one, whatever fails below.
    seed = peekSeed('album', id);
    album = null;
    allTracks = [];
    albumInfo = null;
    albumStatus = 'loading';
    pendingPlay = null;

    const { promise } = entityCache.swr(albumKey(id), () => fetchAlbum(id), (value) => {
      if (seq !== loadSeq) return;
      album = { ...value.album };
      allTracks = value.tracks;
      albumStatus = 'ready';
      // The place is opened before this resolves; this backfills the name once it is known.
      recordPlace(`album:${id}`, value.album.name);
      startPendingPlay();
    });
    promise.catch((e) => {
      if (seq !== loadSeq) return;
      console.error(e);
      if (album) return;
      albumStatus = 'error';
      pendingPlay = null;
    });

    const info = entityCache.swr(albumInfoKey(id), () => fetchAlbumInfo(id), (value) => {
      if (seq === loadSeq) albumInfo = value;
    });
    info.promise.catch((e) => {
      if (seq === loadSeq) console.error(e);
    });
  }

  /**
   * Plays the album, in order or shuffled; pressed before the tracks arrived, it waits for them.
   *
   * @param {boolean} shuffle
   */
  function playAll(shuffle) {
    if (albumStatus === 'loading') {
      pendingPlay = shuffle ? 'shuffle' : 'play';
      return;
    }
    if (allTracks.length === 0) return;
    const list = shuffle ? [...allTracks].sort(() => Math.random() - 0.5) : allTracks;
    currentTrack.set(list[0]);
    startQueue(list, { name: display?.name });
    playerState.update(s => ({ ...s, playing: true, ...(shuffle ? { shuffle: true } : {}) }));
  }

  /** Runs a play that was pressed while the tracks were loading. */
  function startPendingPlay() {
    if (!pendingPlay) return;
    const shuffle = pendingPlay === 'shuffle';
    pendingPlay = null;
    playAll(shuffle);
  }

  $effect(() => {
    const id = albumId;
    const auth = $authParams;
    if (id && auth) {
      untrack(() => loadAlbum());
    }
  });

</script>

{#if !display && albumStatus === 'error'}
  <div class="p-8 text-muma-spotify-text" role="alert">{$t('library.loadFailed')}</div>
{:else}
  <div class="flex flex-col" data-testid="album-page">
    <header class="h-auto md:h-[340px] flex flex-col md:flex-row items-center md:items-end p-6 md:p-8 bg-linear-to-b from-transparent to-black/50 relative gap-6 text-center md:text-left">
       {#if display}
         <img
           src={display.coverArt ? restUrl(`/rest/getCoverArt?id=${display.coverArt}&size=300&${$authParams}`) : '/images/spotify-fallback.svg'}
           alt={display.name}
           class="w-[160px] h-[160px] md:w-[232px] md:h-[232px] object-cover shadow-[0_4px_60px_rgba(0,0,0,0.5)]"
           onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
         />
       {:else}
         <Skeleton class="w-[160px] h-[160px] md:w-[232px] md:h-[232px] shrink-0" />
       {/if}
       <div class="flex flex-col">
         <div class="uppercase text-xs font-bold">{$t('common.album')}</div>
         {#if display?.name}
           <h1 class="text-3xl md:text-5xl lg:text-7xl font-black my-2 leading-tight md:leading-none">{display.name}</h1>
         {:else}
           <div class="my-2 w-64 md:w-[28rem] max-w-full" data-testid="album-name-skeleton"><Skeleton class="h-9 md:h-14 w-full" /></div>
         {/if}
         <div class="flex flex-wrap items-center justify-center md:justify-start gap-4 my-4">
           <button
             class="w-12 h-12 md:w-14 md:h-14 bg-brand rounded-full flex items-center justify-center hover:scale-105 transition-transform shadow-lg border-none cursor-pointer text-black"
             onclick={() => playAll(false)}
             aria-label={$t('common.play')}
             aria-busy={pendingPlay === 'play'}
           >
              {#if pendingPlay === 'play'}
                <Throbber size={20} />
              {:else}
                <svg viewBox="0 0 24 24" width="24" height="24" fill="black">
                  <path d="M7 6v12l10-6z"></path>
                </svg>
              {/if}
           </button>

           <button
             class="w-10 h-10 md:w-12 md:h-12 bg-transparent border border-white/20 rounded-full flex items-center justify-center hover:border-white hover:scale-105 transition-all cursor-pointer text-muma-spotify-text hover:text-white"
             onclick={() => playAll(true)}
             title={$t('common.shufflePlay')}
             aria-busy={pendingPlay === 'shuffle'}
           >
              {#if pendingPlay === 'shuffle'}
                <Throbber size={18} />
              {:else}
                <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                  <path d="M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.45 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z"></path>
                </svg>
              {/if}
           </button>

           <button
             class="bg-transparent border-none p-0 cursor-pointer transition-transform hover:scale-110 disabled:opacity-50 disabled:cursor-default disabled:hover:scale-100 {album?.starred ? 'text-brand' : 'text-muma-spotify-text hover:text-white'}"
             onclick={toggleStar}
             disabled={!album}
             title={album?.starred ? $t('dashboard.removeFavorite') : $t('dashboard.addFavorite')}
           >
              {#if album?.starred}
                <svg viewBox="0 0 24 24" width="32" height="32" fill="currentColor">
                  <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"></path>
                </svg>
              {:else}
                <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"></path>
                </svg>
              {/if}
           </button>
         </div>
         <div class="flex flex-wrap items-center justify-center md:justify-start gap-1 font-bold">
            <ArtistList
              artist={display?.artist}
              artistId={display?.artistId}
              artists={album?.albumArtists}
              onnavigate={onnavigate}
            />
            {#if display?.year} <span class="text-muma-spotify-text hidden md:inline">•</span> {display.year}{/if}
            {#if allTracks.length > 0} <span class="text-muma-spotify-text">•</span> {$t('common.trackCount', { count: allTracks.length })}{/if}
         </div>
       </div>
    </header>

    <div class="p-6 md:p-8 pt-0">
      <SectionState status={albumStatus} onretry={() => loadAlbum()}>
      {#snippet skeleton()}
        <SkeletonRows count={8} />
      {/snippet}
      {#if groupedTracks.length > 0}
        {#each groupedTracks as [disc, tracks] (disc)}
          <div class={hasMultipleDiscs ? "mt-8 first:mt-0" : ""}>
            {#if hasMultipleDiscs}
              <div class="flex items-center gap-4 mb-4 text-muma-spotify-text">
                <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"></path>
                </svg>
                <h3 class="text-lg font-bold">{getDiscTitle(disc)}</h3>
              </div>
            {/if}
            <TrackList {tracks} onnavigate={onnavigate} />
          </div>
        {/each}
      {:else}
        <div class="text-muma-spotify-text p-12 text-center border border-white/5 rounded-xl bg-white/5">
          <p class="text-xl font-bold mb-2 text-white">{$viewMode === 'sets' ? $t('album.noSets') : $t('album.noTracks')}</p>
          <p class="text-sm opacity-60">{$viewMode === 'sets' ? $t('album.noSetsHelp') : $t('album.noTracksHelp')}</p>
        </div>
      {/if}
      </SectionState>

      {#if album?.genre || album?.created}
        <div class="text-muma-spotify-text text-sm mt-8 space-y-1">
            {#if album.genre}<div>{$t('album.genre', { genre: album.genre })}</div>{/if}
            {#if album.created}<div>{$t('album.addedOn', { date: new Date(album.created).toLocaleDateString($locale) })}</div>{/if}
        </div>
      {/if}

      {#if (albumInfo && albumInfo.notes) || (albumInfo && albumInfo.musicBrainzId)}
        <div class="mt-8 border-t border-muma-spotify-light pt-8">
            <h3 class="text-xl font-bold mb-4">{$t('album.about')}</h3>
            {#if albumInfo.notes}
                <p class="text-muma-spotify-text whitespace-pre-wrap mb-4">{albumInfo.notes}</p>
            {/if}
            {#if albumInfo.musicBrainzId}
                <a 
                    href="https://musicbrainz.org/release/{albumInfo.musicBrainzId}" 
                    target="_blank" 
                    rel="noopener noreferrer"
                    class="inline-flex items-center gap-2 text-xs font-bold text-muma-spotify-text hover:text-white transition-colors"
                >
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"></path>
                    </svg>
                    {$t('album.viewOnMusicBrainz')}
                </a>
            {/if}
        </div>
      {/if}
    </div>
  </div>
{/if}

<style>
</style>
