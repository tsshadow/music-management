<script>
  /**
   * The artist page.
   *
   * Renders at once from what the link that opened it already knew (the seed: name, picture) and
   * fills in section by section: the tracks, the releases (from `getArtist`), the biography and
   * similar artists, the MuMa genre chips. The first three requests start together; each section
   * has its own skeleton, error and retry, so one slow or failing part never blanks the page
   * (docs/designs/perceived-performance/). A revisit within a few minutes renders from the
   * entity cache and refreshes in the background.
   */
  import { t } from './i18n/index.js';
  import { untrack } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';
  import { authParams, viewMode, deduplicateEnabled, mumaApiUrl, currentTrack, playerState, hasPermission, restUrl } from './store.js';
  import { getArtistImageUrl } from './utils.js';
  import { getHeaders } from './mumaApi.js';
  import { Pencil } from '@lucide/svelte';
  import { getDeduplicateKey } from './deduplicate.js';
  import { fetchSpotifyTracksPage, spotifyTracksContinuation } from './trackPages.js';
  import ListEnd from './ListEnd.svelte';
  import TrackList from './TrackList.svelte';
  import { SubsonicError } from './subsonic.js';
  import { recordPlace } from './recentPlaces.js';
  import { startQueue } from './queue.js';
  import { openEntity, peekSeed, pressEntity } from './entitySeeds.js';
  import {
    EntityNotFound,
    artistInfoKey,
    artistKey,
    artistTracksKey,
    entityCache,
    fetchArtist,
    fetchArtistInfo,
  } from './entityLoaders.js';
  import Skeleton from './loading/Skeleton.svelte';
  import SkeletonRows from './loading/SkeletonRows.svelte';
  import SkeletonTiles from './loading/SkeletonTiles.svelte';
  import SectionState from './loading/SectionState.svelte';
  import Throbber from './loading/Throbber.svelte';
  import LabelChannels from './LabelChannels.svelte';

  /**
   * @property {string} artistId - The LMS artist id from the route.
   * @property {(view: string) => void} onnavigate - Opens a view.
   * @property {boolean} [canManage] - Whether the user may (un)link channels (rules.manage).
   * @property {() => void} [onmanage] - Opens Management > Downloaders > Links.
   */
  const { artistId, onnavigate, canManage = false, onmanage } = $props();

  /** Subsonic's "the requested data was not found". */
  const SUBSONIC_NOT_FOUND = 70;
  /** The first page of tracks; "load more" asks for pages of 100. */
  const FIRST_PAGE = 25;

  /** What the link that opened this page knew; replaced by `artist` as soon as that arrives. */
  let seed = $state(null);
  /** The server's artist (`getArtist`), or null until it answers. */
  let artist = $state(null);
  /** @type {'loading'|'ready'|'error'|'notfound'} */
  let artistStatus = $state('loading');
  let albumGroups = $state({});
  let appearsOn = $state([]);
  let genres = $state([]);

  let similarArtists = $state([]);
  let biography = $state("");
  let mbid = $state("");

  let allTracks = $state([]);
  /** @type {'loading'|'ready'|'error'} */
  let tracksStatus = $state('loading');
  let allTracksOffset = $state(0);
  let allTracksHasMore = $state(false);
  let seenKeys = new SvelteMap();
  // Whether "Meer laden" appended anything, so a list that ran out ends in "Einde van de lijst".
  let allTracksPagedMore = $state(false);
  let loadingMore = $state(false);
  /** The cache key the tracks on screen belong to; a mode switch changes it. */
  let tracksKey = '';

  /** Play or shuffle pressed before the tracks arrived: started as soon as they do. */
  let pendingPlay = $state(null);

  // Which load is current. Every answer checks it before it writes anything, so the answer for
  // an artist the listener already left can never land on the page of the one they went to.
  let loadSeq = 0;

  /** The header: the server's artist, or the seed standing in for it. */
  const display = $derived(artist ?? (seed ? { ...seed, id: artistId } : null));

  /** The artist's tracks as `getSpotifyTracks` pages them, newest first, songs or sets. */
  function artistTrackParams() {
    return {
      artistId,
      sort: 'recent',
      deduplicate: $deduplicateEnabled ? 'true' : undefined,
      ...($viewMode === 'sets' ? { minDuration: 10 } : { maxDuration: 10 })
    };
  }

  /**
   * Where the artist's track list continues, for a queue started from it
   * (docs/designs/list-continuation/). Pages of 100, like "Meer laden" here.
   */
  const tracksContinuation = $derived(
    allTracksHasMore && allTracks.length > 0
      ? spotifyTracksContinuation(artistTrackParams(), allTracksOffset, { pageSize: 100, dedupe: $deduplicateEnabled, kind: 'artist' })
      : null
  );

  /**
   * Toggles the starred status of the artist.
   */
  async function toggleStar() {
    if (!artist) return;
    const isCurrentlyStarred = !!artist.starred;
    const endpoint = isCurrentlyStarred ? 'unstar' : 'star';

    // Optimistic update, mirrored into the cache so a revisit shows it too.
    setStarred(isCurrentlyStarred ? undefined : new Date().toISOString());

    try {
      const response = await fetch(restUrl(`/rest/${endpoint}?artistId=${artistId}&${$authParams}`));
      if (!response.ok) throw new Error('Failed to toggle star');
    } catch (e) {
      console.error(e);
      // Rollback
      setStarred(isCurrentlyStarred ? new Date().toISOString() : undefined);
    }
  }

  /**
   * Writes the star state to the page and to the cached artist.
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
    artist = apply(artist);
    entityCache.update(artistKey(artistId), apply);
  }

  /**
   * Starts every section of the page for the current `artistId`.
   */
  function loadArtist() {
    if (!$authParams) return;
    const seq = ++loadSeq;
    const id = artistId;
    // Nothing of the previous artist survives into this one, whatever fails below.
    seed = peekSeed('artist', id);
    artist = null;
    artistStatus = 'loading';
    albumGroups = {};
    appearsOn = [];
    genres = [];
    similarArtists = [];
    biography = "";
    mbid = "";
    pendingPlay = null;

    const { promise } = entityCache.swr(artistKey(id), () => fetchArtist(id), (value) => {
      if (seq === loadSeq) applyArtist(value, seq);
    });
    promise.catch((e) => {
      if (seq !== loadSeq) return;
      console.error(e);
      // A failed background refresh leaves a page that is already showing alone.
      if (artist) return;
      artistStatus = isNotFound(e) ? 'notfound' : 'error';
    });

    // Neither needs anything from `getArtist`, so neither waits for it.
    loadAllTracks(false, seq);
    loadArtistInfo(seq);
  }

  /**
   * Whether an error says the artist does not exist, rather than that asking failed.
   *
   * @param {unknown} error
   */
  function isNotFound(error) {
    return error instanceof EntityNotFound
      || (error instanceof SubsonicError && Number(error.code) === SUBSONIC_NOT_FOUND);
  }

  /**
   * Puts the server's artist on the page: the header, the release groups, the recent place and
   * the genre chips.
   *
   * @param {Record<string, any>} artistData
   * @param {number} seq
   */
  function applyArtist(artistData, seq) {
    const nameChanged = artist?.name !== artistData.name;
    artist = { ...artistData };
    artistStatus = 'ready';
    // The place is opened before this resolves (App's handleNavigate records the bare
    // 'artist:<id>'); this backfills the name once it is known.
    recordPlace(`artist:${artistId}`, artistData.name);
    const allAlbums = Array.isArray(artistData.album) ? artistData.album : (artistData.album ? [artistData.album] : []);

    const groups = {};
    const other = [];

    allAlbums.forEach(a => {
      if (a.artist === artistData.name) {
        const type = (a.releaseTypes && a.releaseTypes.length > 0) ? a.releaseTypes[0] : 'Album';
        if (!groups[type]) groups[type] = [];
        groups[type].push(a);
      } else {
        other.push(a);
      }
    });

    albumGroups = groups;
    appearsOn = other;

    if (nameChanged) loadArtistMuma(artistData.name, seq);
  }

  /**
   * Loads all tracks by the artist, filtered by duration based on viewMode. The first page goes
   * through the entity cache, so a revisit shows it at once; "load more" always asks the server.
   *
   * @param {boolean} [append=false] - Whether to append new results to the existing tracks.
   * @param {number} [seq] - The load this belongs to; see `loadSeq`.
   */
  async function loadAllTracks(append = false, seq = loadSeq) {
    if (append) {
      if (loadingMore) return;
      loadingMore = true;
      try {
        const page = await fetchSpotifyTracksPage(artistTrackParams(), allTracksOffset, {
          pageSize: 100,
          seen: $deduplicateEnabled ? seenKeys : null
        });
        if (seq !== loadSeq) return;
        allTracks = [...allTracks, ...page.tracks];
        allTracksOffset = page.nextOffset;
        allTracksHasMore = page.hasMore;
        allTracksPagedMore = true;
      } catch (e) {
        if (seq !== loadSeq) return;
        console.error(e);
        allTracksHasMore = false;
      } finally {
        if (seq === loadSeq) loadingMore = false;
      }
      return;
    }

    const key = artistTracksKey(artistId, $viewMode, $deduplicateEnabled);
    const params = artistTrackParams();
    const dedupe = $deduplicateEnabled;
    tracksKey = key;
    tracksStatus = 'loading';
    allTracks = [];
    allTracksOffset = 0;
    allTracksHasMore = false;
    allTracksPagedMore = false;
    const { promise } = entityCache.swr(
      key,
      () => fetchSpotifyTracksPage(params, 0, { pageSize: FIRST_PAGE, seen: dedupe ? new Map() : null }),
      (page) => {
        if (seq !== loadSeq || tracksKey !== key) return;
        allTracks = page.tracks;
        allTracksOffset = page.nextOffset;
        allTracksHasMore = page.hasMore;
        // The keys "load more" folds against; the same map the page loop built, rebuilt from
        // what it kept.
        seenKeys = new SvelteMap(page.tracks.map((track) => [getDeduplicateKey(track), track]));
        tracksStatus = 'ready';
        startPendingPlay();
      },
    );
    promise.catch((e) => {
      if (seq !== loadSeq || tracksKey !== key) return;
      console.error(e);
      if (tracksStatus !== 'ready') {
        tracksStatus = 'error';
        pendingPlay = null;
      }
    });
  }

  /**
   * Loads additional artist information, such as similar artists. Every field is written on
   * every answer -- empty when this artist has none -- so a field the previous artist had can
   * never stay on screen for this one.
   *
   * @param {number} [seq] - The load this belongs to; see `loadSeq`.
   */
  function loadArtistInfo(seq = loadSeq) {
    const id = artistId;
    const { promise } = entityCache.swr(artistInfoKey(id), () => fetchArtistInfo(id), (info) => {
      if (seq !== loadSeq) return;
      similarArtists = info.similarArtists;
      biography = info.biography;
      mbid = info.mbid;
    });
    // Optional sections: a failure only means they stay away, as they always did.
    promise.catch((e) => {
      if (seq === loadSeq) console.error(e);
    });
  }

  /**
   * Loads the genre rules MuMa holds for this artist.
   *
   * Keyed by name, not by `artistId`: that id comes from LMS and has nothing to do
   * with `library_artists.id`, which is why the previous version of this call
   * (`/api/artists/{artistId}`) hit a route that does not exist and left the chips
   * empty for as long as they have been on the page.
   *
   * @param {string} name - The server's name for the artist, never the seed's.
   * @param {number} [seq] - The load this belongs to; see `loadSeq`.
   */
  async function loadArtistMuma(name, seq = loadSeq) {
    if (!name) return;
    try {
      const response = await fetch(
        `${$mumaApiUrl}/api/curation/artists/${encodeURIComponent(name)}`,
        { headers: getHeaders() });
      if (seq !== loadSeq) return;
      if (response.ok) {
        const data = await response.json();
        if (seq !== loadSeq) return;
        if (data && data.genre_rules) {
          genres = data.genre_rules.map((rule) => ({ name: rule.name }));
        }
      }
    } catch (e) {
      console.error(e);
    }
  }

  /**
   * Plays the artist's tracks, in order (continuing into the next pages) or shuffled. Pressed
   * while the tracks are still on their way, it waits for them instead of doing nothing.
   *
   * @param {boolean} shuffle
   */
  function playAll(shuffle) {
    if (tracksStatus === 'loading') {
      pendingPlay = shuffle ? 'shuffle' : 'play';
      return;
    }
    if (allTracks.length === 0) return;
    if (shuffle) {
      const shuffled = [...allTracks].sort(() => Math.random() - 0.5);
      currentTrack.set(shuffled[0]);
      startQueue(shuffled, { name: display?.name });
      playerState.update(s => ({ ...s, playing: true, shuffle: true }));
      return;
    }
    currentTrack.set(allTracks[0]);
    startQueue(allTracks, { name: display?.name, continuation: tracksContinuation });
    playerState.update(s => ({ ...s, playing: true }));
  }

  /** Runs a play that was pressed while the tracks were loading. */
  function startPendingPlay() {
    if (!pendingPlay) return;
    const shuffle = pendingPlay === 'shuffle';
    pendingPlay = null;
    playAll(shuffle);
  }

  $effect(() => {
    const id = artistId;
    const auth = $authParams;
    if (id && auth) {
      untrack(() => loadArtist());
    }
  });

  // Only the tracks depend on the listening mode and the dedupe switch; the rest stays.
  $effect(() => {
    const key = artistTracksKey(artistId, $viewMode, $deduplicateEnabled);
    untrack(() => {
      if ($authParams && tracksKey && key !== tracksKey) loadAllTracks(false);
    });
  });

  /**
   * Navigates to an album, leaving what the tile knows for its header.
   *
   * @param {Record<string, any>} album
   */
  function openAlbum(album) {
    openEntity(onnavigate, 'album', album);
  }

  /**
   * Navigates to another artist, leaving what the tile knows for its header.
   *
   * @param {Record<string, any>} other
   */
  function openArtist(other) {
    openEntity(onnavigate, 'artist', other);
  }
</script>

{#if !display && (artistStatus === 'notfound' || artistStatus === 'error')}
  <div class="p-8 text-muma-spotify-text" role="alert">{$t('library.loadFailed')}</div>
{:else}
  <div class="flex flex-col" data-testid="artist-page">
    <header class="h-auto md:h-[340px] flex flex-col md:flex-row items-center md:items-end p-6 md:p-8 bg-linear-to-b from-transparent to-black/50 relative gap-6 text-center md:text-left">
       <div class="w-[160px] h-[160px] md:w-[232px] md:h-[232px] flex-shrink-0">
         {#if display}
           <img
             src={getArtistImageUrl(display, $authParams)}
             alt={display.name}
             class="w-full h-full object-cover rounded-full shadow-[0_4px_60px_rgba(0,0,0,0.5)]"
             onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
           />
         {:else}
           <Skeleton class="w-full h-full rounded-full" />
         {/if}
       </div>
       <div class="flex flex-col min-w-0">
         <div class="flex items-center justify-center md:justify-start gap-2 text-sm font-bold mb-2">
            <svg viewBox="0 0 24 24" width="24" height="24" fill="#3d91f4">
                <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10 10-4.5 10-10S17.5 2 12 2zM10 17l-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"></path>
            </svg>
            {$t('artist.verified')}
         </div>
         <div class="flex items-center gap-3 justify-center md:justify-start">
           {#if display?.name}
             <h1 class="text-4xl md:text-7xl lg:text-9xl font-black m-0 leading-tight md:leading-none">{display.name}</h1>
           {:else}
             <div class="w-64 md:w-[28rem] max-w-full" data-testid="artist-name-skeleton"><Skeleton class="h-10 md:h-20 w-full" /></div>
           {/if}
           {#if hasPermission('rules.manage')}
             <button
               class="bg-transparent border-none text-muma-spotify-text hover:text-white transition-all hover:scale-110 cursor-pointer p-1 shrink-0"
               onclick={() => onnavigate?.(`artist-edit:${artistId}`)}
               title={$t('artist.edit')}
               aria-label={$t('artist.edit')}
             >
               <Pencil size={24} />
             </button>
           {/if}
         </div>
         <div class="flex flex-wrap items-center justify-center md:justify-start gap-4 mt-6">
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

           <!-- Disabled until the server has answered: a star on a seed would have nothing to roll
                back to if the artist turned out not to exist. -->
           <button
             class="bg-transparent border-none p-0 cursor-pointer transition-transform hover:scale-110 disabled:opacity-50 disabled:cursor-default disabled:hover:scale-100 {artist?.starred ? 'text-brand' : 'text-muma-spotify-text hover:text-white'}"
             onclick={toggleStar}
             disabled={!artist}
             title={artist?.starred ? $t('dashboard.removeFavorite') : $t('dashboard.addFavorite')}
           >
              {#if artist?.starred}
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
         {#if genres.length > 0}
           <div class="flex flex-wrap gap-2 mt-4">
             {#each genres as genre (genre.name)}
               <span class="px-3 py-1 bg-white/10 hover:bg-white/20 rounded-full text-xs font-bold transition-colors cursor-default border border-white/5">
                 {genre.name}
               </span>
             {/each}
           </div>
         {/if}
       </div>
    </header>

    <div class="p-6 md:p-8 flex flex-col gap-8">
        {#if display?.name}
            <!-- The channels linked to this artist, by name: the route's id is LMS's (issue #126). -->
            <LabelChannels kind="artist" name={display.name} {onnavigate} {canManage} {onmanage} />
        {/if}
        {#if biography || mbid}
            <section>
                <h2 class="text-2xl font-bold mb-4">{$t('artist.about', { name: display?.name ?? '' })}</h2>
                <div class="bg-muma-spotify-panel rounded-xl p-6 md:p-8 relative overflow-hidden group">
                    <div class="relative z-10 max-w-3xl">
                        {#if biography}
                            <p class="text-muma-spotify-text text-sm md:text-base leading-relaxed line-clamp-6 group-hover:line-clamp-none transition-all duration-500 whitespace-pre-wrap mb-4">
                                {biography}
                            </p>
                        {/if}
                        {#if mbid}
                            <a
                                href="https://musicbrainz.org/artist/{mbid}"
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
                    <div class="absolute inset-0 bg-linear-to-t from-black/20 to-transparent pointer-events-none"></div>
                </div>
            </section>
        {/if}

        <section>
            <h2 class="text-2xl font-bold mb-4">{$viewMode === 'sets' ? $t('artist.allSets') : $t('artist.allTracks')}</h2>
            <SectionState status={tracksStatus} onretry={() => loadAllTracks(false)}>
                {#snippet skeleton()}
                    <SkeletonRows count={8} />
                {/snippet}
                {#if allTracks.length > 0}
                    <TrackList tracks={allTracks} continuation={tracksContinuation} onnavigate={onnavigate} />
                    <ListEnd hasMore={allTracksHasMore} ended={allTracksPagedMore} loading={loadingMore} onmore={() => loadAllTracks(true)} testid="artist-tracks-load-more" />
                {:else}
                    <div class="text-muma-spotify-text p-12 text-center border border-white/5 rounded-xl bg-white/5">
                        <p class="text-xl font-bold mb-2 text-white">{$viewMode === 'sets' ? $t('artist.noSets') : $t('artist.noTracks')}</p>
                        <p class="text-sm opacity-60">{$viewMode === 'sets' ? $t('artist.noSetsHelp') : $t('artist.noTracksHelp')}</p>
                    </div>
                {/if}
            </SectionState>
        </section>

        {#if !artist && artistStatus === 'loading'}
            <section data-testid="artist-releases-skeleton">
                <Skeleton class="h-7 w-32 mb-4" />
                <SkeletonTiles count={6} />
            </section>
        {:else if !artist}
            <section>
                <SectionState status="error" onretry={() => loadArtist()} />
            </section>
        {/if}

        {#each Object.entries(albumGroups).sort() as [type, groupAlbums] (type)}
            <section>
                <h2 class="text-2xl font-bold mb-4">{type}s</h2>
                <div class="grid grid-cols-3 gap-3 md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] md:gap-6">
                    {#each groupAlbums as album (album.id)}
                        <div
                          role="button"
                          tabindex="0"
                          class="bg-muma-spotify-panel p-2 md:p-4 rounded-lg transition-colors cursor-pointer hover:bg-muma-spotify-light"
                          onpointerdown={() => pressEntity('album', album)}
                          onclick={() => openAlbum(album)}
                          onkeydown={(e) => e.key === 'Enter' && openAlbum(album)}
                        >
                            <img
                              src={album.coverArt ? restUrl(`/rest/getCoverArt?id=${album.coverArt}&size=300&${$authParams}`) : '/images/spotify-fallback.svg'}
                              alt={album.name}
                              class="w-full aspect-square object-cover mb-2 md:mb-4 rounded shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                              onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
                            />
                            <span class="block font-bold mb-1 whitespace-nowrap overflow-hidden text-ellipsis">{album.name}</span>
                            <span class="text-sm text-muma-spotify-text">{album.year || ''} • {type}</span>
                        </div>
                    {/each}
                </div>
            </section>
        {/each}

        {#if appearsOn.length > 0}
            <section>
                <h2 class="text-2xl font-bold mb-4">{$t('artist.appearsOn')}</h2>
                <div class="grid grid-cols-3 gap-3 md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] md:gap-6">
                    {#each appearsOn as album (album.id)}
                        <div
                          role="button"
                          tabindex="0"
                          class="bg-muma-spotify-panel p-2 md:p-4 rounded-lg transition-colors cursor-pointer hover:bg-muma-spotify-light"
                          onpointerdown={() => pressEntity('album', album)}
                          onclick={() => openAlbum(album)}
                          onkeydown={(e) => e.key === 'Enter' && openAlbum(album)}
                        >
                            <img
                              src={album.coverArt ? restUrl(`/rest/getCoverArt?id=${album.coverArt}&size=300&${$authParams}`) : '/images/spotify-fallback.svg'}
                              alt={album.name}
                              class="w-full aspect-square object-cover mb-2 md:mb-4 rounded shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                              onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
                            />
                            <span class="block font-bold mb-1 whitespace-nowrap overflow-hidden text-ellipsis">{album.name}</span>
                            <span class="text-sm text-muma-spotify-text">{album.artist}</span>
                        </div>
                    {/each}
                </div>
            </section>
        {/if}

        {#if similarArtists.length > 0}
            <section>
                <h2 class="text-2xl font-bold mb-4">{$t('artist.similar')}</h2>
                <div class="grid grid-cols-3 gap-3 md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] md:gap-6">
                    {#each similarArtists as similar (similar.id)}
                        <div
                          role="button"
                          tabindex="0"
                          class="bg-muma-spotify-panel p-2 md:p-4 rounded-lg transition-colors cursor-pointer hover:bg-muma-spotify-light"
                          onpointerdown={() => pressEntity('artist', similar)}
                          onclick={() => openArtist(similar)}
                          onkeydown={(e) => e.key === 'Enter' && openArtist(similar)}
                        >
                            <div class="mb-2 md:mb-4">
                                <img
                                  src={getArtistImageUrl(similar, $authParams)}
                                  alt={similar.name}
                                  class="w-full aspect-square object-cover rounded-full shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                                  onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
                                />
                            </div>
                            <span class="block font-bold mb-1 whitespace-nowrap overflow-hidden text-ellipsis">{similar.name}</span>
                            <span class="text-sm text-muma-spotify-text">{$t('common.artist')}</span>
                        </div>
                    {/each}
                </div>
            </section>
        {/if}
    </div>
  </div>
{/if}
