<script>
  import { openEntity, pressEntity } from './entitySeeds.js';
  import { t } from './i18n/index.js';
  import { fetchGenreTints, withTints } from './genreTints.js';
  import { Pencil } from '@lucide/svelte';
  import { onDestroy, untrack } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';
  import TrackList from './TrackList.svelte';
  import ArtistList from './ArtistList.svelte';
  import DailyMixesShelf from './DailyMixesShelf.svelte';
  import DailyMixesPage from './DailyMixesPage.svelte';
  import FavoritesView from './FavoritesView.svelte';
  import PhoneHome from './PhoneHome.svelte';
  import HomeShelf from './HomeShelf.svelte';
  import OfflineNotice from './OfflineNotice.svelte';
  import PresetGrid from './PresetGrid.svelte';
  // Pages off the first screen, each in its own chunk (lazyViews.js, issues #114 and #118).
  import LazyView from './LazyView.svelte';
  import EntityPageShell from './EntityPageShell.svelte';
  import { lazyViews, listPartsForView } from './lazyViews.js';
  import { lazyComponent } from './lazyComponent.svelte.js';
  import { presets, refreshPresets, createPreset, presetParamsFromFilters } from './presets.js';
  import { formParam } from './trackForm.js';
  import { notify } from './notifications.js';
  import { listOf, offline, subsonicJson, viewHasOfflineSource } from './subsonic.js';
  import { getArtistImageUrl, viewArgument } from './utils.js';
  import WrappedHomeTile from './wrapped/WrappedHomeTile.svelte';
  import { localDateString, memoryCount, memoryHeading, parseMemoryGroups } from './memories.js';
  import { fetchSpotifyTracksPage, spotifyTracksContinuation } from './trackPages.js';
  import { fetchFirstTrackPage, fetchListPage, firstTrackPageSize, listKey, prefetchTrackList, topUpTrackPage, trackListCache, trackListKey } from './trackListCache.js';
  import SectionState from './loading/SectionState.svelte';
  import LabelChannels from './LabelChannels.svelte';
  import SkeletonRows from './loading/SkeletonRows.svelte';
  import SkeletonTiles from './loading/SkeletonTiles.svelte';
  import Throbber from './loading/Throbber.svelte';
  import ListEnd from './ListEnd.svelte';
  import { defaultCollectionState, durationParts, lineupLevel, queryCollection, PLAYLIST_VISIBILITY } from './collections.js';
  import { loadIndexedTags } from './scanTags.js';
  import { DAILY_MIX, DAILY_MIXES, OLD_HITS, RELEASE_RADAR } from './feeds.js';
  import { activeManagementTab, downloaderSubTabRequest, userPermissions } from './store.js';
  import { allSortOptions, authParams, credentials, currentPlaylist, viewMode, favoriteGenres, favoriteLabels, favoritePlaylists, deduplicateEnabled, memoriesOnHomeEnabled, trackPageSize, hasPermission, isMobile, restUrl, mumaUser } from './store.js';

  // Navigation that has to survive a refresh goes through onnavigate, which App turns into a URL.
  // The local assignment stays the fallback for the many places that only switch the screen.
  let { activeView = $bindable('home'), onnavigate = (view) => (activeView = view) } = $props();

  // The list pages' parts that take `bind:` props, so `LazyView` cannot render them (issue #118).
  // Each is fetched when a view that shows it opens -- already there after the boot or idle
  // preload, in the common case.
  const listParts = {
    filterBar: lazyComponent(lazyViews, 'filterBar'),
    collectionBar: lazyComponent(lazyViews, 'collectionBar'),
    collectionGrid: lazyComponent(lazyViews, 'collectionGrid'),
  };
  $effect(() => {
    for (const part of listPartsForView(activeView)) listParts[part].load();
  });
  const FilterBar = $derived(listParts.filterBar.current);
  const CollectionBar = $derived(listParts.collectionBar.current);
  const CollectionGrid = $derived(listParts.collectionGrid.current);

  // LMS's own curated lists, as rows of tracks.
  //
  // MuMa's personalised feeds are not among them any more. The release radar and the daily
  // mixes used to be `feed:` entries here, each fetched for its tracks on every Home load --
  // seconds of server work per row, for a row whose tracks nobody reads on Home. They are cards
  // now (DailyMixesShelf, rendered in the first slot below), drawn from the feed listing alone;
  // a feed's tracks load when its card is opened. The row that used to sit at the top before
  // that was `spotify:release_radar`, the whole library under ten minutes by release date, the
  // same for every listener.
  let sections = $state([
    { titleKey: 'nav.songs', id: 'spotify:songs', tracks: [] },
    { titleKey: 'nav.sets', id: 'spotify:sets', tracks: [] }
  ]);

  let memoryGroups = $state([]);

  // The carousel is a teaser, not the whole feature: it stays a short strip whatever the day holds.
  const MEMORY_CARDS = 10;

  let tracks = $state([]);
  let albums = $state([]);
  let artists = $state([]);
  let allGenres = $state([]);
  // Per-genre colours for the preset tiles; `{}` until MuMa answers, and the tiles fall
  // back to their own palette meanwhile.
  let genreTints = $state({});
  let allLabels = $state([]);
  let allPodcasts = $state([]);
  let allFestivals = $state([]);
  let allYears = $state([]);
  let allLineups = $state([]);
  // null until asked, and null again whenever the answer is not knowable -- see loadIndexedTags.
  let indexedTags = $state(null);
  let playlists = $state([]);
  let tracksOffset = $state(0);
  let tracksHasMore = $state(true);
  // Whether "Meer laden" appended anything to the list on screen, so a list that ran out ends in
  // "Einde van de lijst" and one that fit on its first page ends in nothing.
  let tracksPagedMore = $state(false);
  let albumsOffset = $state(0);
  let albumsHasMore = $state(true);
  let artistsOffset = $state(0);
  let artistsHasMore = $state(true);
  const pageSize = $derived($trackPageSize);
  let currentGenre = $state('');
  let currentSort = $state('recent');
  let currentYear = $state('');
  let currentTrackSearch = $state('');
  let currentMinRating = $state('2');
  let includeUnrated = $state(true);
  let currentMinQuality = $state('');
  // The sets view's Soort filter ('' = all). Sent only in the sets view, see formParam.
  let currentForm = $state('');
  let currentSeed = $state(Math.floor(Math.random() * 1000000));
  let sentinel = $state(null);

  // Sort/filter state for the three collection grids. They keep their own copy
  // so switching between Genres and Labels doesn't carry a search term across.
  let genreView = $state(defaultCollectionState('genres'));
  let labelView = $state(defaultCollectionState('labels'));
  let podcastView = $state(defaultCollectionState('podcasts'));
  let festivalView = $state(defaultCollectionState('festivals'));
  let yearView = $state(defaultCollectionState('years'));
  let lineupView = $state(defaultCollectionState('lineups'));
  /**
   * The Lineups page walks a tree rather than listing every path at once: the server
   * reports the stage, its edition and its festival as three separate lineups, which
   * flattened is a few hundred cards of mostly repetition.
   *
   * The level is part of the view identifier, so every step has its own URL and the
   * back button walks back up.
   */
  const lineupPath = $derived(activeView.startsWith('lineups:') ? viewArgument(activeView) : '');
  const lineupTree = $derived(lineupLevel(allLineups, lineupPath, lineupView.search));
  const lineupEntries = $derived(lineupTree.entries);
  const lineupCrumbs = $derived(lineupTree.crumbs);

  /** A level opens deeper; a stage, a flat file or the level itself opens its tracks. */
  function openLineupEntry(entry) {
    activeView = entry.hasChildren ? `lineups:${entry.value}` : `lineup:${entry.value}`;
  }
  let playlistView = $state(defaultCollectionState('playlists'));

  const visiblePlaylists = $derived(
    queryCollection(playlists, 'playlists', playlistView, {
      favorites: $favoritePlaylists,
      username: $credentials.username
    })
  );

  let currentArtistSort = $state('alphabetical');
  let currentArtistRole = $state('all');
  let currentArtistSearch = $state('');

  let currentAlbumSort = $state('newest');
  let currentAlbumGenre = $state('');
  let currentAlbumSearch = $state('');

  // The collection grids' (genres, labels...) own loading flag. The track list has its own
  // below: one shared flag let a finished grid load mark a still-loading track list as done.
  let isLoading = $state(false);
  let seenKeys = new SvelteMap();

  // What the track list shows while its answer is on its way (issue #109,
  // docs/designs/perceived-performance/). `loading`: skeleton rows, because nothing on screen
  // belongs to this place yet. `error`: the section's error line with a retry. `ready`: rows (or
  // the empty state). `tracksStale` marks rows that belong to the same place under the previous
  // filters: they stay, dimmed, until the new answer replaces them. A new place never keeps the
  // previous place's rows -- that was the bug: the old genre's list under the new genre's name.
  let tracksStatus = $state('ready');
  let tracksStale = $state(false);
  // A background refresh of rows that came from the cache, or of dimmed stale rows.
  let tracksRefreshing = $state(false);
  let tracksLoading = $state(false);
  // The view the rows on screen belong to, and a counter that makes a late answer harmless.
  let tracksPlace = null;
  let tracksLoadSeq = 0;

  // The search results page's artists and albums, kept apart from the Artists and Albums grids
  // so neither shows the other's rows while its own answer is on its way (issue #112).
  let searchArtists = $state([]);
  let searchAlbums = $state([]);
  let searchArtistsStatus = $state('ready');
  let searchAlbumsStatus = $state('ready');
  let searchSeq = 0;

  let tracksController;
  let albumsController;
  let artistsController;

  /**
   * Fetches tracks for a specific curated playlist, by its Subsonic playlist id.
   *
   * @param {string} id - The Subsonic ID of the curated playlist.
   * @returns {Promise<Object[]>} A promise that resolves to an array of tracks.
   */
  async function fetchTracks(id) {
    if (!$authParams) return [];

    console.log(`Fetching tracks for curated playlist: ${id}`);
    try {
        const response = await fetch(restUrl(`/rest/getSpotifyPlaylist?id=${encodeURIComponent(id)}&seed=${currentSeed}&${$authParams}`));
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        console.log(`Data for ${id}:`, data);
        const result = data['subsonic-response']?.playlist?.entry || [];
        return Array.isArray(result) ? result : [result];
    } catch (e) {
        console.error(`Failed to fetch ${id}:`, e);
        return [];
    }
  }

  /**
   * The query every track list on this page asks `getSpotifyTracks` -- the songs and sets lists,
   * a genre, label, podcast, festival, year or lineup, search -- without `offset`/`count`, which
   * the pager adds. One function, so the page and the queue it starts ask the same question.
   *
   * `view` and `filters` exist for the press prefetch, which asks the question of a view that is
   * not on screen yet, with the filters as they will be once it is.
   *
   * @param {string} [view] - Defaults to the view on screen.
   * @param {{genre: string, year: string, query: string}} [filters] - The filter bar's genre,
   *   year and search; default to the current ones.
   * @returns {Record<string, unknown>}
   */
  function trackQueryParams(view = activeView, filters = { genre: currentGenre, year: currentYear, query: currentTrackSearch }) {
    const argument = viewArgument(view);
    return {
      sort: currentSort,
      seed: currentSort === 'random' ? currentSeed : undefined,
      deduplicate: $deduplicateEnabled ? 'true' : undefined,
      query: filters.query || undefined,
      genre: filters.genre || (view.startsWith('genre:') ? argument : undefined),
      label: view.startsWith('label:') ? argument : undefined,
      podcast: view.startsWith('podcast:') ? argument : undefined,
      festival: view.startsWith('festival:') ? argument : undefined,
      lineup: view.startsWith('lineup:') ? argument : undefined,
      // The year view reuses the parameter the filter bar already drives. Seeding
      // `currentYear` from the route instead would not survive: resetTrackFiltersFor
      // clears it on every arrival at a new track view, before the first fetch.
      year: filters.year || (view.startsWith('year:') ? argument : undefined),
      minRating: currentMinRating !== '0' ? currentMinRating : undefined,
      includeUnrated: includeUnrated ? 'true' : undefined,
      minQuality: currentMinQuality || undefined,
      form: formParam(currentForm, $viewMode),
      // Minutes on this endpoint, not seconds; the offline library reads them
      // the same way. Ten is the songs/sets boundary the whole app uses.
      ...($viewMode === 'sets' ? { minDuration: 10 } : { maxDuration: 10 })
    };
  }

  /**
   * Where the track list on screen continues, for the queue a row tap or play starts from it
   * (docs/designs/list-continuation/): the same query from `tracksOffset` on. Null once the list
   * has nothing more, so a list that fit on one page hands the queue no continuation.
   */
  const tracksContinuation = $derived(
    tracksHasMore && tracks.length > 0
      ? spotifyTracksContinuation(trackQueryParams(), tracksOffset, { pageSize, dedupe: $deduplicateEnabled })
      : null
  );

  /**
   * Puts a first page -- fresh or from the cache -- on screen, with where the list continues and
   * the version keys it has folded together so far.
   *
   * @param {{tracks: object[], nextOffset: number, hasMore: boolean, seen: Array<[string, object]>|null}} page
   */
  function applyFirstPage(page) {
    tracks = page.tracks;
    tracksHasMore = page.hasMore;
    tracksOffset = page.nextOffset;
    seenKeys = new SvelteMap(page.seen ?? []);
  }

  /**
   * Loads the track list of the songs and sets views, a genre, label, podcast, festival, year or
   * lineup, and the search results page.
   *
   * The first page goes through `trackListCache` (stale-while-revalidate): a list seen in the
   * last few minutes is on screen at once and refreshed in the background, and a press on a card
   * may already have started the request. Without a cached copy, a new place starts from skeleton
   * rows and a filter change on the same place dims the rows it replaces (issue #109).
   *
   * Without a cached copy the first request asks only `firstTrackPageSize(pageSize)` rows (50),
   * so the first rows appear in the time a short answer takes even when the listener's page size
   * is 200 and LMS is slow; `topUpFirstPage` then fetches the rest of the page behind them. A
   * background refresh of cached rows asks the whole page at once, so the rows on screen never
   * shrink to 50 and grow back.
   *
   * @param {boolean} [append=false] - Load the next page onto the list instead.
   */
  async function loadAllTracks(append = false) {
    if (!$authParams) return;
    if (append) return loadMoreTracks();

    const seq = ++tracksLoadSeq;
    tracksController?.abort();
    tracksController = new AbortController();
    const signal = tracksController.signal;
    tracksPagedMore = false;

    const params = trackQueryParams();
    const options = { pageSize, dedupe: $deduplicateEnabled };
    const key = trackListKey(params, options);
    const place = activeView;
    const cached = trackListCache.peek(key);
    if (cached) {
      applyFirstPage(cached.value);
      tracksStatus = 'ready';
      tracksStale = false;
    } else if (place !== tracksPlace || tracks.length === 0) {
      tracks = [];
      tracksOffset = 0;
      tracksHasMore = true;
      seenKeys = new SvelteMap();
      tracksStatus = 'loading';
      tracksStale = false;
    } else {
      tracksStale = true;
      tracksStatus = 'ready';
    }
    tracksPlace = place;
    if (cached?.fresh) {
      tracksRefreshing = false;
      tracksLoading = false;
      // A cached copy of the small first page (a press prefetch, or a top-up that never finished)
      // is filled up now.
      topUpFirstPage(seq, params, key, options, signal);
      return;
    }

    // Rows from the cache stay usable while they refresh: "load more" may go on from them.
    const blocking = !cached;
    tracksRefreshing = Boolean(cached) || tracksStale;
    if (blocking) tracksLoading = true;
    const count = blocking ? firstTrackPageSize(pageSize) : pageSize;
    let applied = false;
    try {
      const page = await trackListCache.load(
        key,
        () => fetchFirstTrackPage(params, { ...options, count, signal }),
        { force: true }
      );
      // Another load started meanwhile, or the listener has added pages to the cached rows
      // since: a refresh must not throw those away.
      if (seq !== tracksLoadSeq || tracksPagedMore) return;
      applyFirstPage(page);
      tracksStatus = 'ready';
      applied = true;
    } catch (e) {
      if (seq !== tracksLoadSeq || e.name === 'AbortError') return;
      console.error('Failed to load tracks:', e);
      // A refused call is not more to fetch: stop paging. Rows from the cache may stay, as a
      // failed refresh never blanks a list; stale rows from other filters may not.
      tracksHasMore = false;
      if (!cached) {
        tracks = [];
        // Offline, the list is empty because nothing is downloaded, which the empty state
        // explains; online it is a failure, which gets the section's retry.
        tracksStatus = $offline ? 'ready' : 'error';
      }
    } finally {
      if (seq === tracksLoadSeq) {
        tracksStale = false;
        tracksRefreshing = false;
        if (blocking) tracksLoading = false;
      }
    }
    if (applied) await topUpFirstPage(seq, params, key, options, signal);
  }

  /**
   * Fills the first page on screen up to `pageSize` when it holds fewer rows and the list has
   * more: the small first request, or a cached copy of one. Runs behind rows that are already
   * usable; `tracksLoading` holds "load more" and the scroll sentinel off meanwhile, so the two
   * never fetch the same offset. The filled page replaces the cache entry, so a revisit shows the
   * whole page at once. Versions are folded against the page's own keys (`seenKeys`), on a copy.
   *
   * A failure leaves the rows and `tracksHasMore` as they were, so "load more" can try again.
   *
   * @param {number} seq - The `tracksLoadSeq` of the load this belongs to.
   * @param {Record<string, unknown>} params - The list's query.
   * @param {string} key - Its cache key.
   * @param {{pageSize: number, dedupe: boolean}} options
   * @param {AbortSignal} signal - Aborted when the listener moves on.
   */
  async function topUpFirstPage(seq, params, key, options, signal) {
    if (seq !== tracksLoadSeq || !tracksHasMore || tracks.length >= options.pageSize) return;
    tracksLoading = true;
    try {
      const shown = {
        tracks,
        nextOffset: tracksOffset,
        hasMore: tracksHasMore,
        seen: options.dedupe ? [...seenKeys.entries()] : null
      };
      const page = await topUpTrackPage(params, shown, { pageSize: options.pageSize, signal });
      trackListCache.set(key, page);
      if (seq !== tracksLoadSeq || tracksPagedMore) return;
      applyFirstPage(page);
    } catch (e) {
      if (seq !== tracksLoadSeq || e.name === 'AbortError') return;
      console.error('Failed to load the rest of the first page:', e);
    } finally {
      if (seq === tracksLoadSeq) tracksLoading = false;
    }
  }

  /** Appends the next page of the track list on screen ("Meer laden", the scroll sentinel). */
  async function loadMoreTracks() {
    // `tracksLoading`: a top-up or another "load more" is already fetching the next offset.
    if (!tracksHasMore || tracksStatus !== 'ready' || tracksLoading) return;
    const seq = tracksLoadSeq;
    const signal = tracksController?.signal;
    tracksLoading = true;
    try {
      const page = await fetchSpotifyTracksPage(trackQueryParams(), tracksOffset, {
        pageSize,
        seen: $deduplicateEnabled ? seenKeys : null,
        signal
      });
      if (seq !== tracksLoadSeq) return;
      tracksHasMore = page.hasMore;
      tracksOffset = page.nextOffset;
      tracks = [...tracks, ...page.tracks];
      tracksPagedMore = true;
    } catch (e) {
      if (seq !== tracksLoadSeq || e.name === 'AbortError') return;
      console.error('Failed to load more tracks:', e);
      tracksHasMore = false;
    } finally {
      if (seq === tracksLoadSeq) tracksLoading = false;
    }
  }

  /**
   * A finger (or mouse button) went down on a genre, label, podcast, festival, year or lineup
   * card: start that list's first page, which the page then picks up from the cache. One request
   * per press, never on hover or scroll (docs/designs/perceived-performance/, "Prefetch on press
   * only"). The filters are the ones the view will have: arriving at a different list clears the
   * filter bar's genre, year and search (`resetTrackFiltersFor`), returning to the same one does
   * not.
   *
   * @param {string} view - e.g. `genre:Hardcore`.
   */
  function prefetchTrackView(view) {
    if (!$authParams || $offline) return;
    const filters = view === lastTrackView ? undefined : { genre: '', year: '', query: '' };
    prefetchTrackList(trackQueryParams(view, filters), { pageSize, dedupe: $deduplicateEnabled });
  }

  /**
   * Loads one section of the search results page -- its artists or its albums -- through the same
   * cache as the track lists. The section shows skeleton tiles until its answer, and its own
   * error and retry if that fails; the page's other sections never wait for it (issue #112).
   *
   * @param {'artists'|'albums'} kind
   * @param {string} query
   * @param {number} [seq] - The search this belongs to; a later search makes the answer moot.
   */
  function loadSearchSection(kind, query, seq = searchSeq) {
    const isAlbums = kind === 'albums';
    const method = isAlbums ? 'getAlbumList2' : 'getArtistList';
    const path = isAlbums ? 'albumList2.album' : 'artistList.artist';
    const params = isAlbums
      ? { type: currentAlbumSort, size: pageSize, offset: 0, genre: currentAlbumGenre || undefined, query }
      : { type: currentArtistSort, role: currentArtistRole, size: pageSize, offset: 0, query };
    const show = (rows, status) => {
      if (seq !== searchSeq) return;
      if (isAlbums) {
        searchAlbums = rows;
        searchAlbumsStatus = status;
      } else {
        searchArtists = rows;
        searchArtistsStatus = status;
      }
    };
    const { cached, promise } = trackListCache.swr(
      listKey(method, params),
      () => fetchListPage(method, params, path),
      (rows) => show(rows, 'ready')
    );
    if (cached === null) show([], 'loading');
    promise.catch((e) => {
      console.error(`Failed to search ${kind}:`, e);
      if (cached === null) show([], $offline ? 'ready' : 'error');
    });
  }

  /** Starts every section of the search results page for `query`, dropping any older search. */
  function loadSearch(query) {
    const seq = ++searchSeq;
    loadAllTracks();
    loadSearchSection('artists', query, seq);
    loadSearchSection('albums', query, seq);
  }

  // Whether any section of the search results page is still waiting for its first answer or
  // refreshing: the heading says "searching" meanwhile, and "No results" waits for all of them.
  const searchPending = $derived(
    tracksStatus === 'loading' || tracksRefreshing || searchArtistsStatus === 'loading' || searchAlbumsStatus === 'loading'
  );
  const searchEmpty = $derived(
    !searchPending &&
      tracksStatus === 'ready' && searchArtistsStatus === 'ready' && searchAlbumsStatus === 'ready' &&
      tracks.length === 0 && searchArtists.length === 0 && searchAlbums.length === 0
  );

  /**
   * Loads a list of albums with sorting, filtering, and pagination.
   *
   * @param {boolean} [append=false] - Whether to append new results to the existing albums.
   */
  async function loadAlbums(append = false) {
    if (!$authParams) return;
    if (!append) {
      albumsOffset = 0;
      albumsHasMore = true;
      if (albumsController) {
        albumsController.abort();
      }
      albumsController = new AbortController();
    }
    if (!albumsHasMore) return;

    const signal = albumsController?.signal;

    try {
      const data = await subsonicJson(
        'getAlbumList2',
        {
          type: currentAlbumSort,
          size: pageSize,
          offset: albumsOffset,
          genre: currentAlbumGenre || undefined,
          query: currentAlbumSearch || undefined
        },
        { signal }
      );
      const newAlbums = listOf(data, 'albumList2.album');

      if (append) {
        albums = [...albums, ...newAlbums];
      } else {
        albums = newAlbums;
      }

      albumsOffset += newAlbums.length;
      albumsHasMore = newAlbums.length === pageSize;
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error(e);
      albumsHasMore = false;
      if (!append) albums = [];
    }
  }

  /**
   * Loads a list of artists with sorting, filtering, and pagination.
   *
   * @param {boolean} [append=false] - Whether to append new results to the existing artists.
   */
  async function loadArtists(append = false) {
    if (!$authParams) return;
    if (!append) {
      artistsOffset = 0;
      artistsHasMore = true;
      if (artistsController) {
        artistsController.abort();
      }
      artistsController = new AbortController();
    }
    if (!artistsHasMore) return;

    const signal = artistsController?.signal;

    try {
      const data = await subsonicJson(
        'getArtistList',
        {
          type: currentArtistSort,
          role: currentArtistRole,
          size: pageSize,
          offset: artistsOffset,
          query: currentArtistSearch || undefined
        },
        { signal }
      );
      const newArtists = listOf(data, 'artistList.artist');

      if (append) {
        artists = [...artists, ...newArtists];
      } else {
        artists = newArtists;
      }

      artistsOffset += newArtists.length;
      artistsHasMore = newArtists.length === pageSize;
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error(e);
      artistsHasMore = false;
      if (!append) artists = [];
    }
  }

  /**
   * Loads all user playlists from the server.
   */
  async function loadPlaylists() {
    if (!$authParams) return;
    try {
      const data = await subsonicJson('getPlaylists');
      playlists = listOf(data, 'playlists.playlist');
    } catch (e) { console.error(e); }
  }

  // The presets follow the MuMa account, not the Subsonic login: they are that user's dynamic
  // playlists. Reloaded whenever the account changes, which includes signing in after a boot
  // that started logged out.
  $effect(() => {
    const userId = $mumaUser?.id;
    if (!userId) {
      presets.set([]);
      return;
    }
    refreshPresets(userId);
    fetchGenreTints().then((tints) => (genreTints = tints));
  });

  // `hasPermission` reads its stores with `get`, so a template call is not re-run when the
  // permissions arrive after the first render (a label page opened by URL). Reading the two
  // stores here makes this one reactive.
  const canManageRules = $derived.by(() => {
    void $userPermissions;
    void $mumaUser;
    return hasPermission('rules.manage');
  });

  /** Opens Management > Downloaders on its Links tab, where a curator (un)links channels (issue #122). */
  function openChannelLinks() {
    downloaderSubTabRequest.set('links');
    activeManagementTab.set('downloaders');
    activeView = 'management';
  }

  /**
   * Saves the list on screen -- its genre/label/year, sort, rating floor and mode -- as a preset
   * tile on the home screen. The name is the only thing asked for; everything else is what the
   * filter bar already says.
   */
  async function saveCurrentAsPreset() {
    const userId = $mumaUser?.id;
    if (!userId) return;
    const argument = viewArgument(activeView);
    const name = prompt($t('presets.namePrompt'), defaultPresetName());
    if (!name?.trim()) return;
    try {
      await createPreset(userId, {
        name: name.trim(),
        params: presetParamsFromFilters({
          genre: currentGenre || (activeView.startsWith('genre:') ? argument : ''),
          label: activeView.startsWith('label:') ? argument : '',
          year: currentYear || (activeView.startsWith('year:') ? argument : ''),
          sort: currentSort,
          minRating: currentMinRating,
          minQuality: currentMinQuality,
          form: currentForm,
          viewMode: $viewMode,
        }),
      });
      await refreshPresets(userId);
      notify.success($t('presets.saved'));
    } catch (e) {
      console.error(e);
      notify.error($t('presets.saveFailed'));
    }
  }

  /**
   * What the player header says a queue started from this list is playing from. The whole
   * songs/sets view is named after its sort as well -- "Nummers · Recent uitgebracht" -- because
   * "Nummers" alone told the listener nothing about the list they picked a track from. A genre,
   * label or year view already has a name of its own (`placeTitle`), so those pass null and keep
   * it.
   */
  const listSourceName = $derived.by(() => {
    if (activeView !== 'songs' && activeView !== 'sets') return null;
    const base = $viewMode === 'sets' ? $t('nav.sets') : $t('nav.songs');
    const sortKey = allSortOptions.songs.find((option) => option.id === currentSort)?.labelKey;
    return sortKey ? `${base} · ${$t(sortKey)}` : base;
  });

  /** "Random Uptempo Hardcore", "Recent Hardstyle (2024)": the sort word first, as the old tiles were named. */
  function defaultPresetName() {
    const argument = viewArgument(activeView);
    const subject = currentGenre || (activeView.startsWith('genre:') || activeView.startsWith('label:') ? argument : '')
      || ($viewMode === 'sets' ? $t('nav.sets') : $t('nav.songs'));
    const year = currentYear || (activeView.startsWith('year:') ? argument : '');
    const sortWord = currentSort === 'random' ? $t('presets.randomWord') : currentSort === 'recent' ? $t('presets.recentWord') : '';
    return `${sortWord} ${subject}${year ? ` (${year})` : ''}`.trim();
  }

  /**
   * Loads all genres from the server.
   */
  async function loadAllGenres() {
    if (!$authParams) return;
    isLoading = true;
    console.log("Fetching all genres...");
    try {
      // Kept unfiltered and unsorted: the CollectionBar owns both now, so the
      // "minimaal" chips can reach the long tail instead of it being dropped here.
      const genres = listOf(await subsonicJson('getGenres'), 'genres.genre');
      // getGenres carries no colour. MuMa derives one per genre so this list and the
      // mobile app draw Hardstyle in the same orange; a genre MuMa does not know keeps
      // the brand accent.
      allGenres = withTints(genres, await fetchGenreTints());
      console.log(`Loaded ${allGenres.length} genres`);
    } catch (e) {
      console.error("Failed to load genres:", e);
    } finally {
      isLoading = false;
    }
  }

  /**
   * Loads all record labels from the server.
   */
  async function loadAllLabels() {
    if (!$authParams) return;
    isLoading = true;
    try {
      allLabels = listOf(await subsonicJson('getRecordLabels'), 'recordLabels.recordLabel');
    } catch (e) {
      console.error("Failed to load labels:", e);
    } finally {
      isLoading = false;
    }
  }

  /**
   * Loads the radio shows and podcast series from the server.
   *
   * `getTags` answers for one cluster type, so this only returns something once
   * PODCAST is in the LMS scanner's extra tags to scan and the library has been
   * rescanned. An empty list is therefore a normal state, not an error.
   */
  async function loadAllPodcasts() {
    if (!$authParams) return;
    isLoading = true;
    try {
      const response = await fetch(restUrl(`/rest/getTags?name=PODCAST&${$authParams}`));
      const data = await response.json();
      const result = data['subsonic-response']?.tags?.tag || [];
      allPodcasts = Array.isArray(result) ? result : [result];
    } catch (e) {
      console.error("Failed to load podcasts:", e);
    } finally {
      isLoading = false;
    }
  }

  /**
   * Loads one cluster-type list (festivals, years) and, when it comes back empty,
   * the scanner settings that say whether the tag is indexed at all.
   *
   * @param {string} tag - The cluster type, e.g. 'FESTIVAL'.
   * @returns {Promise<Object[]>} The tags, possibly empty.
   */
  async function loadTagCollection(tag) {
    if (!$authParams) return [];
    isLoading = true;
    try {
      const response = await fetch(restUrl(`/rest/getTags?name=${tag}&${$authParams}`));
      const data = await response.json();
      const result = data['subsonic-response']?.tags?.tag || [];
      const list = Array.isArray(result) ? result : [result];

      // Only worth a second request when there is something to explain.
      indexedTags = list.length === 0 ? await loadIndexedTags($authParams) : null;

      return list;
    } catch (e) {
      console.error(`Failed to load the ${tag} list:`, e);
      return [];
    } finally {
      isLoading = false;
    }
  }

  /**
   * Loads the festival lineups.
   *
   * These are text files on disk rather than anything the library knows about, so an
   * empty list is the normal state of a server where nobody has added one yet.
   */
  async function loadAllLineups() {
    if (!$authParams) return;
    isLoading = true;
    try {
      const response = await fetch(restUrl(`/rest/getLineups?${$authParams}`));
      const data = await response.json();
      const result = data['subsonic-response']?.lineups?.lineup || [];
      const list = Array.isArray(result) ? result : [result];
      // getLineups answers with a `name` attribute; every collection here keys on `value`.
      allLineups = list.map((entry) => ({ value: entry.name ?? entry.value }));
    } catch (e) {
      console.error('Failed to load lineups:', e);
    } finally {
      isLoading = false;
    }
  }

  /**
   * The extra line under an empty festival or year grid: shown only when the scanner
   * settings were readable AND actually lack the tag. A null `indexedTags` means the
   * settings could not be read -- a non-admin, an older server -- and then the page
   * says nothing rather than pointing at a setting the viewer cannot see.
   *
   * @param {string} tag
   * @returns {string|null}
   */
  function tagHint(tag) {
    if (indexedTags === null) return null;
    if (indexedTags.includes(tag)) return null;
    return $t('collection.tagNotIndexed', { tag });
  }

  /**
   * Adds or removes one entry in a favorites store, keeping it sorted so the
   * value that gets synced to the account doesn't churn on every toggle.
   *
   * @param {import('svelte/store').Writable<string[]>} store
   * @param {string} key
   */
  function toggleFavoriteIn(store, key) {
    store.update(favs => (favs.includes(key) ? favs.filter(f => f !== key) : [...favs, key].sort()));
  }

  /**
   * Toggles a genre as favorite.
   *
   * @param {string} genre - The genre name.
   */
  function toggleFavorite(genre) {
    toggleFavoriteIn(favoriteGenres, genre);
  }

  /**
   * A playlist's total playing time, in the units of the active locale.
   *
   * @param {number|string} seconds
   * @returns {string}
   */
  function playlistLength(seconds) {
    const { hours, minutes } = durationParts(seconds);
    const minutePart = $t('collection.minutesShort', { count: minutes });
    return hours > 0 ? `${$t('collection.hoursShort', { count: hours })} ${minutePart}` : minutePart;
  }

  /**
   * Opens the "Release Radar" curated playlist.
   */
  function openRadar() {
      openPlaylist({ id: 'spotify:release_radar', name: 'Release Radar', coverArt: 'spotify:release_radar' });
  }

  /**
   * Switches the view to the details of a specific playlist.
   *
   * @param {Object} playlist - The playlist object.
   */
  function openPlaylist(playlist) {
    currentPlaylist.set(playlist);
    activeView = 'playlist-detail';
  }

  /**
   * Clears the FilterBar's track filters.
   *
   * Called whenever the track list is entered from somewhere else -- a genre,
   * a label, a search. Those views share one set of filter variables, so
   * without this a genre picked on the Songs screen, or a leftover search
   * term, silently narrows the label you just tapped and the list comes back
   * near-empty for no reason the screen explains.
   */
  function resetTrackFilters() {
      currentGenre = '';
      currentYear = '';
      currentTrackSearch = '';
  }

  // The last track-list view the filters were reset for. Guards against
  // wiping a filter the user just set when the effect re-runs for another
  // reason, such as toggling between songs and sets.
  let lastTrackView = null;

  /**
   * Resets the track filters when arriving at a different track list than the
   * one currently on screen.
   *
   * @param {string} view
   */
  function resetTrackFiltersFor(view) {
      if (view === lastTrackView) return;
      lastTrackView = view;
      resetTrackFilters();
  }

  /**
   * Handles changes from the FilterBar and reloads the appropriate data.
   *
   * @param {Object} params - The filter and sort parameters.
   */
  function handleFilterChange(params) {
      const { genre, sort, year, search, role, minRating, includeUnrated: incUnrated, minQuality, form } = params;
      currentSeed = Math.floor(Math.random() * 1000000);
      if (activeView === 'artists') {
          currentArtistSort = sort;
          currentArtistRole = role;
          currentArtistSearch = search;
          loadArtists();
      } else if (activeView === 'albums') {
          currentAlbumSort = sort;
          currentAlbumGenre = genre;
          currentAlbumSearch = search;
          loadAlbums();
      } else {
          currentGenre = genre;
          currentSort = sort;
          currentYear = year;
          currentTrackSearch = search;
          currentMinRating = minRating || '0';
          includeUnrated = incUnrated !== undefined ? incUnrated : true;
          currentMinQuality = minQuality || '';
          currentForm = form || '';
          loadAllTracks();
      }
  }

  /** One curated section's tracks, plus whether it actually loaded. */
  async function fetchSection(section) {
    return { tracks: await fetchTracks(section.id), failed: false };
  }

  let curatedLoad = 0;

  /** Publishes each Home section independently; older loads cannot replace newer results. */
  async function loadCurated() {
    const load = ++curatedLoad;
    await Promise.all(sections.map(async (section) => {
      let result;
      try {
        result = await fetchSection(section);
      } catch {
        result = { tracks: [], failed: true };
      }
      if (load !== curatedLoad) return;
      sections = sections.map((current) => current.id === section.id ? { ...current, ...result } : current);
    }));
  }

  /**
   * Loads the memory groups for the home carousel.
   *
   * Failure is deliberately silent: a server that does not know the endpoint simply has no
   * memories, and an error banner on the home screen would be worse than an absent row.
   */
  async function loadMemoryGroups() {
    if (!$authParams || !$memoriesOnHomeEnabled) {
      memoryGroups = [];
      return;
    }

    try {
      const response = await fetch(restUrl(`/rest/getMemories?date=${localDateString()}&${$authParams}`));
      if (!response.ok) return;

      const data = await response.json();
      memoryGroups = parseMemoryGroups(data).slice(0, MEMORY_CARDS);
    } catch (e) {
      console.error('Failed to load memories for the home screen:', e);
      memoryGroups = [];
    }
  }

  /**
   * Whether `view` shows the `getSpotifyTracks` list this page loads through `loadAllTracks`.
   *
   * @param {string} view
   * @returns {boolean}
   */
  function isTrackListView(view) {
    return (
      view === 'songs' || view === 'sets' || view.startsWith('search:') ||
      ['genre:', 'label:', 'podcast:', 'festival:', 'year:', 'lineup:'].some((prefix) => view.startsWith(prefix))
    );
  }

  // A list request outliving the page would keep its connection busy for nothing.
  onDestroy(() => tracksController?.abort());

  $effect(() => {
    const view = activeView;
    const auth = $authParams;
    const _mode = $viewMode;
    // A dependency on purpose: coming back online has to re-run the loader for
    // the view the listener is already standing on.
    const unreachable = $offline && !viewHasOfflineSource(view);

    // Leaving the track lists stops their request: a 200-row answer during an LMS scan holds a
    // connection for seconds that the page the listener moved to needs.
    if (!isTrackListView(view)) untrack(() => tracksController?.abort());

    if (auth && !unreachable) {
      untrack(() => {
        if (view === 'home') {
            loadCurated();
            loadMemoryGroups();
        } else if (view === 'songs' || view === 'sets' || view.startsWith('genre:') || view.startsWith('label:') || view.startsWith('podcast:') || view.startsWith('festival:') || view.startsWith('year:') || view.startsWith('lineup:')) {
            resetTrackFiltersFor(view);
            loadAllTracks();
        } else if (view === 'radar') {
            openRadar();
        } else if (view === 'albums') {
            loadAlbums();
        } else if (view === 'genres') {
            loadAllGenres();
        } else if (view === 'labels') {
            loadAllLabels();
        } else if (view === 'podcasts') {
            loadAllPodcasts();
        } else if (view === 'festivals') {
            loadTagCollection('FESTIVAL').then((list) => (allFestivals = list));
        } else if (view === 'years') {
            loadTagCollection('YEAR').then((list) => (allYears = list));
        } else if (view === 'lineups' || view.startsWith('lineups:')) {
            loadAllLineups();
        } else if (view === 'artists') {
            loadArtists();
        } else if (view === 'playlists') {
            loadPlaylists();
        } else if (view.startsWith('search:')) {
            resetTrackFiltersFor(view);
            currentTrackSearch = viewArgument(view);
            currentAlbumSearch = currentTrackSearch;
            currentArtistSearch = currentTrackSearch;
            loadSearch(currentTrackSearch);
        }
      });
    }
  });

  $effect(() => {
    if (sentinel && tracksHasMore && !tracksLoading && tracksStatus === 'ready' && (activeView === 'songs' || activeView === 'sets' || activeView.startsWith('genre:') || activeView.startsWith('label:') || activeView.startsWith('podcast:') || activeView.startsWith('festival:') || activeView.startsWith('year:') || activeView.startsWith('lineup:') || activeView.startsWith('search:'))) {
      const observer = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting) {
          loadAllTracks(true);
        }
      }, { threshold: 0.1 });
      observer.observe(sentinel);
      return () => observer.disconnect();
    }
  });
</script>

<!--
  Shown when a collection has items but the current sort/filter selection
  matches none of them. Distinct from the "you have no genres at all" message:
  this one is the user's own doing and offers a way back.
-->
{#snippet noMatches(clear)}
  <div class="text-muma-spotify-text p-12 text-center border border-white/5 rounded-xl bg-white/5">
    <p class="text-xl font-bold mb-2 text-white">{$t('collection.noMatches')}</p>
    <p class="text-sm opacity-60 mb-4">{$t('collection.noMatchesHelp')}</p>
    <button
      class="bg-transparent border border-muma-spotify-muted text-white px-6 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]"
      onclick={clear}
    >{$t('collection.clearFilters')}</button>
  </div>
{/snippet}

<div class="flex flex-col gap-8">
  <!-- Checked before every other branch, and before any loader runs, so a view
       whose only data source is the server says so in one line instead of
       spinning at a request that cannot be answered. -->
  {#if $offline && !viewHasOfflineSource(activeView)}
    <OfflineNotice kind="unavailable" onnavigate={onnavigate} />
  {:else if activeView === 'downloads'}
    <LazyView name="downloads" props={{ onnavigate }} />
  {:else if activeView === 'favorites'}
    <FavoritesView presets={$presets} tints={genreTints} canCreate={Boolean($mumaUser)} {onnavigate} />
  {:else if activeView === 'home'}
    {#if $isMobile}
      <PhoneHome {memoryGroups} {onnavigate} onrecent={(sort) => { currentSort = sort; onnavigate($viewMode); }} />
    {:else}
    <PresetGrid presets={$presets} tints={genreTints} canCreate={Boolean($mumaUser)} onopen={(preset) => onnavigate(`preset:${preset.id}`)} oncreate={() => onnavigate('new-preset')} />
    <WrappedHomeTile {onnavigate} />
    {#if $memoriesOnHomeEnabled && memoryGroups.length > 0}
      <section class="flex flex-col gap-4">
        <div class="flex justify-between items-end mb-4">
          <h2 class="text-2xl font-bold m-0">{$t('memories.title')}</h2>
          <button
            class="bg-transparent border-none text-muma-spotify-text text-[12px] font-bold cursor-pointer uppercase tracking-[0.1em] hover:underline"
            onclick={() => onnavigate('memories')}
          >{$t('dashboard.showAll')}</button>
        </div>
        <div class="flex gap-4 overflow-x-auto scrollbar-hide pb-2">
          {#each memoryGroups as group (group.year)}
            <button
              class="flex-shrink-0 w-40 text-left bg-transparent border-none cursor-pointer p-0"
              onclick={() => onnavigate(`memories:${group.year}`)}
            >
              <img
                class="w-40 h-40 object-cover mb-2 rounded-md"
                src={group.songs[0]?.coverArt
                  ? restUrl(`/rest/getCoverArt?id=${group.songs[0].coverArt}&size=300&${$authParams}`)
                  : '/images/spotify-fallback.svg'}
                alt=""
              />
              <div class="text-white font-bold text-sm">
                {$t(memoryHeading(group).key, memoryHeading(group).vars)}
              </div>
              <div class="text-muma-spotify-text text-xs">
                {group.year} • {$t('common.trackCount', { count: memoryCount(group) })}
              </div>
            </button>
          {/each}
        </div>
      </section>
    {/if}
    <DailyMixesShelf radar onnavigate={(v) => activeView = v} />
    {#each sections as section (section.id)}
      <HomeShelf
        title={$t(section.titleKey)}
        tracks={section.tracks.slice(0, 6)}
        noTracksText={$t('dashboard.noTracksInSection')}
        showAllLabel={$t('dashboard.showAll')}
        onnavigate={(v) => activeView = v}
        onshowall={() => {
          if (section.id === 'spotify:songs') {
            viewMode.set('songs');
            activeView = 'songs';
          } else if (section.id === 'spotify:sets') {
            viewMode.set('sets');
            activeView = 'sets';
          }
        }}
      />
    {/each}
    {/if}
  {:else if activeView === 'songs' || activeView === 'sets' || activeView.startsWith('genre:') || activeView.startsWith('label:') || activeView.startsWith('podcast:') || activeView.startsWith('festival:') || activeView.startsWith('year:') || activeView.startsWith('lineup:')}
    <div class="flex flex-col gap-4 mb-6">
        <h2 class="text-2xl font-bold m-0 flex items-center gap-3">
            {#if activeView === 'songs' || activeView === 'sets'}
              {$viewMode === 'sets' ? $t('dashboard.sets') : $t('dashboard.allTracks')}
            {:else if activeView.startsWith('genre:')}
              {@const genreName = viewArgument(activeView)}
              <span>{genreName}</span>
              {#if hasPermission('rules.manage')}
                <button
                  class="bg-transparent border-none text-muma-spotify-text hover:text-white transition-all hover:scale-110 cursor-pointer p-1"
                  onclick={() => activeView = `genre-edit:${genreName}`}
                  title={$t('dashboard.editGenre')}
                  aria-label={$t('dashboard.editGenre')}
                >
                  <Pencil size={20} />
                </button>
              {/if}
              <button
                class="bg-transparent border-none text-brand transition-all hover:scale-110 active:scale-95 cursor-pointer p-1"
                onclick={() => toggleFavorite(genreName)}
                title={$favoriteGenres.includes(genreName) ? $t('dashboard.removeFavorite') : $t('dashboard.addFavorite')}
              >
                <svg viewBox="0 0 24 24" width="24" height="24" fill={$favoriteGenres.includes(genreName) ? "currentColor" : "none"} stroke="currentColor" stroke-width="2">
                    <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"></path>
                </svg>
              </button>
            {:else}
              {@const collectionName = viewArgument(activeView)}
              <span>{collectionName}</span>
              {#if activeView.startsWith('label:') && hasPermission('rules.manage')}
                <button
                  class="bg-transparent border-none text-muma-spotify-text hover:text-white transition-all hover:scale-110 cursor-pointer p-1"
                  onclick={() => activeView = `label-edit:${collectionName}`}
                  title={$t('dashboard.editLabel')}
                  aria-label={$t('dashboard.editLabel')}
                >
                  <Pencil size={20} />
                </button>
              {/if}
            {/if}
            {#if tracksRefreshing}
              <!-- The rows below are on screen but a newer answer is on its way. -->
              <span class="text-muma-spotify-text"><Throbber /></span>
            {/if}
            {#if $mumaUser && (activeView === 'songs' || activeView === 'sets' || activeView.startsWith('genre:') || activeView.startsWith('label:') || activeView.startsWith('year:'))}
              <!-- Saves this list as a home tile. Only the views whose filters a tile can
                   carry offer it; a podcast or a lineup has no cluster in the tile format. -->
              <button
                class="ml-auto shrink-0 flex items-center gap-1.5 bg-transparent border border-muma-spotify-muted hover:border-white text-white text-xs font-bold px-3 py-1.5 rounded-full cursor-pointer transition-colors whitespace-nowrap"
                onclick={saveCurrentAsPreset}
                title={$t('presets.save')}
              >
                <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" aria-hidden="true">
                  <path d="M17 3H7c-1.1 0-2 .9-2 2v16l7-3 7 3V5c0-1.1-.9-2-2-2zm-4 10h-2v-2H9V9h2V7h2v2h2v2h-2v2z"></path>
                </svg>
                <span class="hidden sm:inline">{$t('presets.save')}</span>
              </button>
            {/if}
        </h2>
        {#if FilterBar}
          <FilterBar view="songs" bind:genre={currentGenre} bind:sort={currentSort} bind:year={currentYear} bind:search={currentTrackSearch} bind:minRating={currentMinRating} bind:includeUnrated={includeUnrated} bind:minQuality={currentMinQuality} bind:form={currentForm} showForm={$viewMode === 'sets'} showGenre={!activeView.startsWith('genre:') && !activeView.startsWith('label:') && !activeView.startsWith('podcast:')} showYear={!activeView.startsWith('year:')} onchange={handleFilterChange} />
        {/if}
    </div>
    {#if activeView.startsWith('label:')}
      <!-- The channels linked to this label, as a section of its own (issue #122). -->
      <LabelChannels
        kind="label"
        name={viewArgument(activeView)}
        onnavigate={(v) => activeView = v}
        canManage={canManageRules}
        onmanage={openChannelLinks}
      />
    {/if}
    <!-- The header above comes from the route, so it names the new place at once; the rows
         below never belong to the previous place (issue #109). -->
    <SectionState status={tracksStatus} onretry={() => loadAllTracks()}>
      {#snippet skeleton()}
        <SkeletonRows count={10} />
      {/snippet}
        {#if tracks.length > 0}
            <!-- Rows of the same place under the previous filters: kept, dimmed, until the
                 new answer replaces them (styleguide, Loading States: Stale results). -->
            <div class="transition-opacity duration-200 {tracksStale ? 'opacity-50' : ''}" aria-busy={tracksStale} data-testid="track-list-rows" data-stale={tracksStale ? 'true' : undefined}>
                <TrackList {tracks} sourceName={listSourceName} continuation={tracksContinuation} onnavigate={(v) => activeView = v} />
            </div>
            <div bind:this={sentinel}>
                <ListEnd hasMore={tracksHasMore} ended={tracksPagedMore} loading={tracksLoading} onmore={() => loadAllTracks(true)} testid="tracks-load-more" />
            </div>
        {:else if $offline}
            <!-- The list is empty and there is no connection, so the reason is
                 that nothing here is downloaded -- not that the library is empty. -->
            <OfflineNotice kind="empty" onnavigate={onnavigate} />
        {:else}
            <div class="text-muma-spotify-text p-12 text-center border border-white/5 rounded-xl bg-white/5">
                <p class="text-xl font-bold mb-2 text-white">{$viewMode === 'sets' ? $t('dashboard.noSets') : $t('dashboard.noTracks')}</p>
                <p class="text-sm opacity-60">{$viewMode === 'sets' ? $t('dashboard.noSetsHelp') : $t('dashboard.noTracksHelp')}</p>
            </div>
        {/if}
    </SectionState>
  {:else if activeView === 'albums'}
    <div class="flex flex-col gap-4 mb-6">
      <h2 class="text-2xl font-bold m-0">{$t('nav.albums')}</h2>
      {#if FilterBar}
        <FilterBar view="albums" bind:genre={currentAlbumGenre} bind:sort={currentAlbumSort} bind:search={currentAlbumSearch} onchange={handleFilterChange} />
      {/if}
    </div>
    {#if albums.length > 0}
        <div class="grid grid-cols-3 gap-3 md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] md:gap-6">
            {#each albums as album (album.id)}
                <div
                  role="button"
                  tabindex="0"
                  class="bg-muma-spotify-panel p-2 md:p-4 rounded-lg flex flex-col gap-1.5 md:gap-3 cursor-pointer transition-colors hover:bg-muma-spotify-light"
                  onpointerdown={() => pressEntity('album', album)}
                  onclick={() => openEntity((v) => activeView = v, 'album', album)}
                  onkeydown={(e) => e.key === 'Enter' && openEntity((v) => activeView = v, 'album', album)}
                >
                    <img
                      src={album.coverArt ? restUrl(`/rest/getCoverArt?id=${album.coverArt}&size=300&${$authParams}`) : '/images/spotify-fallback.svg'}
                      alt={album.name}
                      class="w-full aspect-square object-cover rounded shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                      onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
                    />
                    <span class="font-bold whitespace-nowrap overflow-hidden text-ellipsis">{album.name}</span>
                    <ArtistList
                      artist={album.artist}
                      artistId={album.artistId}
                      artists={album.albumArtists}
                      onnavigate={(v) => activeView = v}
                    />
                </div>
            {/each}
        </div>
    {:else}
        <div class="text-muma-spotify-text p-12 text-center border border-white/5 rounded-xl bg-white/5">
            <p class="text-xl font-bold mb-2 text-white">{$t('dashboard.noAlbums')}</p>
            <p class="text-sm opacity-60">{$t('dashboard.noAlbumsHelp')}</p>
        </div>
    {/if}
    {#if albumsHasMore}
        <div class="flex justify-center py-6">
            <button class="bg-transparent border border-muma-spotify-muted text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]" onclick={() => loadAlbums(true)}>{$t('common.loadMore')}</button>
        </div>
    {/if}
  {:else if activeView === 'genres'}
    {#if CollectionGrid}
      <CollectionGrid
        type="genres"
        title={$t('nav.genres')}
        items={allGenres}
        bind:state={genreView}
        loading={isLoading}
        favorites={$favoriteGenres}
        onfavorite={(value) => toggleFavorite(value)}
        emptyText={$t('dashboard.noGenres')}
        onselect={(item) => (activeView = `genre:${item.value}`)}
        onpress={(item) => prefetchTrackView(`genre:${item.value}`)}
      />
    {:else}
      <SkeletonTiles count={12} />
    {/if}
  {:else if activeView === 'podcasts'}
    {#if CollectionGrid}
      <CollectionGrid
        type="podcasts"
        title={$t('nav.podcasts')}
        items={allPodcasts}
        bind:state={podcastView}
        loading={isLoading}
        emptyText={$t('collection.noPodcasts')}
        onselect={(item) => (activeView = `podcast:${item.value}`)}
        onpress={(item) => prefetchTrackView(`podcast:${item.value}`)}
      />
    {:else}
      <SkeletonTiles count={12} />
    {/if}
  {:else if activeView === 'labels'}
    {#if CollectionGrid}
      <CollectionGrid
        type="labels"
        title={$t('nav.labels')}
        items={allLabels}
        bind:state={labelView}
        loading={isLoading}
        favorites={$favoriteLabels}
        onfavorite={(value) => toggleFavoriteIn(favoriteLabels, value)}
        favoriteAriaLabel={$t('collection.toggleFavoriteLabel')}
        emptyText={$t('dashboard.noLabels')}
        onselect={(item) => (activeView = `label:${item.value}`)}
        onpress={(item) => prefetchTrackView(`label:${item.value}`)}
      />
    {:else}
      <SkeletonTiles count={12} />
    {/if}
  {:else if activeView === 'festivals'}
    {#if CollectionGrid}
      <CollectionGrid
        type="festivals"
        title={$t('nav.festivals')}
        items={allFestivals}
        bind:state={festivalView}
        loading={isLoading}
        emptyText={$t('collection.noFestivals')}
        emptyHint={tagHint('FESTIVAL')}
        onselect={(item) => (activeView = `festival:${item.value}`)}
        onpress={(item) => prefetchTrackView(`festival:${item.value}`)}
      />
    {:else}
      <SkeletonTiles count={12} />
    {/if}
  {:else if activeView === 'years'}
    {#if CollectionGrid}
      <CollectionGrid
        type="years"
        title={$t('nav.years')}
        items={allYears}
        bind:state={yearView}
        loading={isLoading}
        emptyText={$t('collection.noYears')}
        emptyHint={tagHint('YEAR')}
        onselect={(item) => (activeView = `year:${item.value}`)}
        onpress={(item) => prefetchTrackView(`year:${item.value}`)}
      />
    {:else}
      <SkeletonTiles count={12} />
    {/if}
  {:else if activeView === 'lineups' || activeView.startsWith('lineups:')}
    {#if lineupCrumbs.length > 0}
      <nav class="flex flex-wrap items-center gap-2 text-sm text-muma-spotify-text mb-4" aria-label={$t('nav.lineups')}>
        <button class="bg-transparent border-0 p-0 text-inherit cursor-pointer hover:text-white hover:underline" onclick={() => (activeView = 'lineups')}>
          {$t('nav.lineups')}
        </button>
        {#each lineupCrumbs as crumb, index (crumb.value)}
          <span aria-hidden="true">/</span>
          {#if index === lineupCrumbs.length - 1}
            <span class="text-white">{crumb.label}</span>
          {:else}
            <button class="bg-transparent border-0 p-0 text-inherit cursor-pointer hover:text-white hover:underline" onclick={() => (activeView = `lineups:${crumb.value}`)}>
              {crumb.label}
            </button>
          {/if}
        {/each}
      </nav>
    {/if}
    {#if CollectionGrid}
      <CollectionGrid
        type="lineups"
        title={lineupCrumbs.length > 0 ? lineupCrumbs[lineupCrumbs.length - 1].label : $t('nav.lineups')}
        items={lineupEntries}
        bind:state={lineupView}
        loading={isLoading}
        emptyText={$t('collection.noLineups')}
        emptyHint={$t('collection.noLineupsHelp')}
        onselect={openLineupEntry}
        onpress={(entry) => { if (!entry.hasChildren) prefetchTrackView(`lineup:${entry.value}`); }}
      />
    {:else}
      <SkeletonTiles count={12} />
    {/if}
  {:else if activeView === 'artists'}
    <div class="flex flex-col gap-4 mb-6">
      <h2 class="text-2xl font-bold m-0">{$t('nav.artists')}</h2>
      {#if FilterBar}
        <FilterBar view="artists" bind:sort={currentArtistSort} bind:role={currentArtistRole} bind:search={currentArtistSearch} onchange={handleFilterChange} />
      {/if}
    </div>
    <div class="grid grid-cols-3 gap-3 md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] md:gap-6">
        {#each artists as artist (artist.id)}
            <div
              role="button"
              tabindex="0"
              class="bg-muma-spotify-panel p-2 md:p-4 rounded-lg flex flex-col gap-1.5 md:gap-3 cursor-pointer transition-colors hover:bg-muma-spotify-light"
              onpointerdown={() => pressEntity('artist', artist)}
              onclick={() => openEntity((v) => activeView = v, 'artist', artist)}
              onkeydown={(e) => e.key === 'Enter' && openEntity((v) => activeView = v, 'artist', artist)}
            >
                <img
                  src={getArtistImageUrl(artist, $authParams)}
                  alt={artist.name}
                  class="w-full aspect-square object-cover rounded-full shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                  onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
                />
                <span class="font-bold whitespace-nowrap overflow-hidden text-ellipsis">{artist.name}</span>
                <span class="text-sm text-muma-spotify-text whitespace-nowrap overflow-hidden text-ellipsis">{$t('common.artist')}</span>
            </div>
        {/each}
    </div>
    {#if artistsHasMore}
        <div class="flex justify-center py-6">
            <button class="bg-transparent border border-muma-spotify-muted text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]" onclick={() => loadArtists(true)}>{$t('common.loadMore')}</button>
        </div>
    {/if}
  {:else if activeView === 'playlists'}
    <div class="flex flex-col gap-4 mb-6">
      <h2 class="text-2xl font-bold m-0">{$t('nav.playlists')}</h2>
      {#if CollectionBar}
        <CollectionBar
          type="playlists"
          bind:state={playlistView}
          total={playlists.length}
          shown={visiblePlaylists.length}
          favoriteCount={$favoritePlaylists.length}
          visibilityOptions={PLAYLIST_VISIBILITY}
        />
      {/if}
    </div>
    {#if playlists.length === 0}
        <div class="text-muma-spotify-text p-12 text-center border border-white/5 rounded-xl bg-white/5">
            <p class="text-xl font-bold mb-2 text-white">{$t('dashboard.noPlaylists')}</p>
            <p class="text-sm opacity-60">{$t('dashboard.noPlaylistsHelp')}</p>
        </div>
    {:else if visiblePlaylists.length === 0}
        {@render noMatches(() => (playlistView = defaultCollectionState('playlists')))}
    {:else if $isMobile}
    <!-- Spotify's own Library tab lists playlists rather than tiling them; a phone screen has
         room for one column of real information (name, track count, length) but not for a
         cover big enough to tell two playlists apart, so a row with a small thumbnail reads
         better here than the desktop's cover grid. -->
    <div class="flex flex-col" role="list">
        {#each visiblePlaylists as playlist (playlist.id)}
            <div
              role="button"
              tabindex="0"
              class="flex items-center gap-3 py-2 cursor-pointer rounded hover:bg-white/5 active:bg-white/10"
              onclick={() => openPlaylist(playlist)}
              onkeydown={(e) => e.key === 'Enter' && openPlaylist(playlist)}
            >
                <img
                  src={playlist.coverArt ? restUrl(`/rest/getCoverArt?id=${playlist.coverArt}&size=112&${$authParams}`) : '/images/spotify-fallback.svg'}
                  alt=""
                  class="w-14 h-14 object-cover rounded shrink-0"
                  onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
                />
                <div class="flex flex-col min-w-0 flex-1">
                  <span class="font-bold truncate">{playlist.name}</span>
                  <span class="text-xs text-muma-spotify-text truncate">
                    {$t('common.trackCount', { count: Number(playlist.songCount) || 0 })}
                    {#if Number(playlist.duration) > 0}
                      &middot; {playlistLength(playlist.duration)}
                    {/if}
                  </span>
                </div>
                <button
                    class="p-2 shrink-0 text-brand {$favoritePlaylists.includes(String(playlist.id)) ? '' : 'opacity-40'}"
                    onclick={(e) => { e.stopPropagation(); toggleFavoriteIn(favoritePlaylists, String(playlist.id)); }}
                    aria-label={$t('collection.toggleFavoritePlaylist')}
                >
                    <svg viewBox="0 0 24 24" width="18" height="18" fill={$favoritePlaylists.includes(String(playlist.id)) ? "currentColor" : "none"} stroke="currentColor" stroke-width="2">
                        <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"></path>
                    </svg>
                </button>
            </div>
        {/each}
    </div>
    {:else}
    <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
        {#each visiblePlaylists as playlist (playlist.id)}
            <div
              role="button"
              tabindex="0"
              class="bg-muma-spotify-panel p-4 rounded-lg flex flex-col gap-3 cursor-pointer transition-colors hover:bg-muma-spotify-light relative group"
              onclick={() => openPlaylist(playlist)}
              onkeydown={(e) => e.key === 'Enter' && openPlaylist(playlist)}
            >
                <img
                  src={playlist.coverArt ? restUrl(`/rest/getCoverArt?id=${playlist.coverArt}&size=300&${$authParams}`) : '/images/spotify-fallback.svg'}
                  alt={playlist.name}
                  class="w-full aspect-square object-cover rounded shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                  onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
                />
                <button
                    class="absolute top-6 right-6 p-2 bg-black/40 rounded-full text-brand transition-all hover:scale-110 active:scale-95 {$favoritePlaylists.includes(String(playlist.id)) ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}"
                    onclick={(e) => { e.stopPropagation(); toggleFavoriteIn(favoritePlaylists, String(playlist.id)); }}
                    aria-label={$t('collection.toggleFavoritePlaylist')}
                >
                    <svg viewBox="0 0 24 24" width="18" height="18" fill={$favoritePlaylists.includes(String(playlist.id)) ? "currentColor" : "none"} stroke="currentColor" stroke-width="2">
                        <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"></path>
                    </svg>
                </button>
                <span class="font-bold whitespace-nowrap overflow-hidden text-ellipsis">{playlist.name}</span>
                <span class="text-xs text-muma-spotify-text whitespace-nowrap overflow-hidden text-ellipsis">
                  {$t('common.trackCount', { count: Number(playlist.songCount) || 0 })}
                  {#if Number(playlist.duration) > 0}
                    &middot; {playlistLength(playlist.duration)}
                  {/if}
                </span>
            </div>
        {/each}
    </div>
    {/if}
  {:else if activeView === 'playlist-detail'}
    <LazyView name="playlistPage" props={{ onnavigate: (v) => activeView = v }} />
  {:else if activeView.startsWith('artist-edit:')}
    <LazyView name="artistEdit" props={{ artistId: viewArgument(activeView), onback: () => activeView = `artist:${viewArgument(activeView)}` }} />
  {:else if activeView.startsWith('label-edit:')}
    <LazyView name="labelEdit" props={{ name: viewArgument(activeView), onback: () => activeView = `label:${viewArgument(activeView)}`, onnavigate: (v) => activeView = v, onmanage: openChannelLinks }} />
  {:else if activeView.startsWith('genre-edit:')}
    <LazyView name="genreEdit" props={{ name: viewArgument(activeView), onback: () => activeView = `genre:${viewArgument(activeView)}` }} />
  {:else if activeView.startsWith('artist:')}
    <!-- Keyed on the id: going from one artist straight to another remounts the view instead of
         reusing it with the previous artist's fields still in place. -->
    {#key viewArgument(activeView)}
      <!-- The page is its own chunk; until it is in, the seeded header keeps the heading on
           screen from the first frame (issue #118, optimistic navigation of #107). -->
      <LazyView name="artistPage" props={{ artistId: viewArgument(activeView), onnavigate: (v) => activeView = v, canManage: canManageRules, onmanage: openChannelLinks }}>
        {#snippet placeholder()}
          <EntityPageShell kind="artist" id={viewArgument(activeView)} />
        {/snippet}
      </LazyView>
    {/key}
  {:else if activeView.startsWith('album:')}
    {#key viewArgument(activeView)}
      <LazyView name="albumPage" props={{ albumId: viewArgument(activeView), onnavigate: (v) => activeView = v }}>
        {#snippet placeholder()}
          <EntityPageShell kind="album" id={viewArgument(activeView)} />
        {/snippet}
      </LazyView>
    {/key}
  {:else if activeView.startsWith('song:')}
    <LazyView name="song" props={{ workId: viewArgument(activeView), onnavigate: (v) => activeView = v }} />
  {:else if activeView.startsWith('search:')}
    <!-- Every section loads on its own and says so: skeletons until its first answer, its own
         error line with a retry, and "No results" only once all three have answered empty
         (issue #112). Rows of an earlier search never stand under this one's heading. -->
    <div class="flex flex-col gap-8" aria-busy={searchPending}>
      <h2 class="text-2xl font-bold m-0 flex items-center gap-3">
        <span>{$viewMode === 'sets' ? $t('dashboard.searchResultsSets', { query: viewArgument(activeView) }) : $t('dashboard.searchResultsTracks', { query: viewArgument(activeView) })}</span>
        {#if searchPending}
          <span class="text-muma-spotify-text text-sm font-normal flex items-center gap-2" data-testid="search-pending">
            <Throbber label={$t('search.searching')} />
            <span class="hidden sm:inline">{$t('search.searching')}</span>
          </span>
        {/if}
      </h2>

      {#if tracksStatus !== 'ready' || tracks.length > 0}
        <section>
          <h3 class="text-xl font-bold mb-4">{$viewMode === 'sets' ? $t('dashboard.sets') : $t('dashboard.tracks')}</h3>
          <SectionState status={tracksStatus} onretry={() => loadAllTracks()}>
            {#snippet skeleton()}
              <SkeletonRows count={5} />
            {/snippet}
            <div class="transition-opacity duration-200 {tracksStale ? 'opacity-50' : ''}" data-testid="search-track-rows">
              <TrackList {tracks} continuation={tracksContinuation} onnavigate={(v) => activeView = v} />
            </div>
            <!-- Search results page like any other track list, and continue in the queue the same way
                 (docs/designs/list-continuation/). -->
            <div bind:this={sentinel}>
              <ListEnd hasMore={tracksHasMore} ended={tracksPagedMore} loading={tracksLoading} onmore={() => loadAllTracks(true)} testid="tracks-load-more" />
            </div>
          </SectionState>
        </section>
      {/if}

      {#if searchArtistsStatus !== 'ready' || searchArtists.length > 0}
        <section>
          <h3 class="text-xl font-bold mb-4">{$t('nav.artists')}</h3>
          <SectionState status={searchArtistsStatus} onretry={() => loadSearchSection('artists', viewArgument(activeView))}>
            {#snippet skeleton()}
              <SkeletonTiles count={6} round />
            {/snippet}
            <div class="grid grid-cols-3 gap-3 md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] md:gap-6">
              {#each searchArtists as artist (artist.id)}
                <div
                  role="button"
                  tabindex="0"
                  class="bg-muma-spotify-panel p-2 md:p-4 rounded-lg flex flex-col gap-1.5 md:gap-3 cursor-pointer transition-colors hover:bg-muma-spotify-light"
                  onpointerdown={() => pressEntity('artist', artist)}
                  onclick={() => openEntity((v) => activeView = v, 'artist', artist)}
                  onkeydown={(e) => e.key === 'Enter' && openEntity((v) => activeView = v, 'artist', artist)}
                >
                    <img
                      src={getArtistImageUrl(artist, $authParams)}
                      alt={artist.name}
                      class="w-full aspect-square object-cover rounded-full shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                      onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
                    />
                    <span class="font-bold whitespace-nowrap overflow-hidden text-ellipsis">{artist.name}</span>
                    <span class="text-sm text-muma-spotify-text">{$t('common.artist')}</span>
                </div>
              {/each}
            </div>
          </SectionState>
        </section>
      {/if}

      {#if searchAlbumsStatus !== 'ready' || searchAlbums.length > 0}
        <section>
          <h3 class="text-xl font-bold mb-4">{$t('nav.albums')}</h3>
          <SectionState status={searchAlbumsStatus} onretry={() => loadSearchSection('albums', viewArgument(activeView))}>
            {#snippet skeleton()}
              <SkeletonTiles count={6} />
            {/snippet}
            <div class="grid grid-cols-3 gap-3 md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] md:gap-6">
              {#each searchAlbums as album (album.id)}
                <div
                  role="button"
                  tabindex="0"
                  class="bg-muma-spotify-panel p-2 md:p-4 rounded-lg flex flex-col gap-1.5 md:gap-3 cursor-pointer transition-colors hover:bg-muma-spotify-light"
                  onpointerdown={() => pressEntity('album', album)}
                  onclick={() => openEntity((v) => activeView = v, 'album', album)}
                  onkeydown={(e) => e.key === 'Enter' && openEntity((v) => activeView = v, 'album', album)}
                >
                    <img
                      src={album.coverArt ? restUrl(`/rest/getCoverArt?id=${album.coverArt}&size=300&${$authParams}`) : '/images/spotify-fallback.svg'}
                      alt={album.name}
                      class="w-full aspect-square object-cover rounded shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                      onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
                    />
                    <span class="font-bold whitespace-nowrap overflow-hidden text-ellipsis">{album.name}</span>
                    <ArtistList
                      artist={album.artist}
                      artistId={album.artistId}
                      artists={album.albumArtists}
                      onnavigate={(v) => activeView = v}
                    />
                </div>
              {/each}
            </div>
          </SectionState>
        </section>
      {/if}

      {#if searchEmpty}
        {#if $offline}
          <!-- Search does reach the device; finding nothing there means nothing
               matching is downloaded, which is not "try another term". -->
          <OfflineNotice kind="empty" onnavigate={onnavigate} />
        {:else}
          <div class="text-muma-spotify-text p-12 text-center border border-white/5 rounded-xl bg-white/5">
              <p class="text-xl font-bold mb-2 text-white">{$t('search.noResults')}</p>
              <p class="text-sm opacity-60">{$t('search.tryAnother')}</p>
          </div>
        {/if}
      {/if}
    </div>
  {:else if activeView === 'settings'}
    <LazyView name="settings" props={{ onnavigate }} />
  {:else if activeView === 'management'}
    <LazyView name="management" />
  {:else if activeView === 'history'}
    <LazyView name="history" props={{ onnavigate: (v) => activeView = v }} />
  {:else if activeView === 'bpm'}
    <LazyView name="bpm" props={{ onnavigate: (v) => onnavigate(v) }} />
  {:else if activeView === 'radio'}
    <LazyView name="radio" />
  {:else if activeView === 'listening'}
    <LazyView name="listening" props={{ onnavigate: (v) => onnavigate(v) }} />
  {:else if activeView === 'starred'}
    <LazyView name="starred" props={{ onnavigate: (v) => activeView = v }} />
  {:else if activeView === 'release-radar'}
    <LazyView name="feedPage" props={{ slug: RELEASE_RADAR, onnavigate: (v) => onnavigate(v) }} />
  {:else if activeView === 'daily-mix'}
    <LazyView name="feedPage" props={{ slug: DAILY_MIX, onnavigate: (v) => onnavigate(v) }} />
  {:else if DAILY_MIXES.includes(activeView) || activeView === OLD_HITS}
    {#key activeView}
      <LazyView name="feedPage" props={{ slug: activeView, onnavigate: (v) => onnavigate(v) }} />
    {/key}
  {:else if activeView === 'daily-mixes'}
    <DailyMixesPage onnavigate={(v) => onnavigate(v)} />
  {:else if activeView === 'new-preset'}
    <LazyView name="presetBuilder" props={{ onnavigate: (v) => onnavigate(v) }} />
  {:else if activeView.startsWith('preset-edit:')}
    {@const preset = $presets.find((p) => p.id === viewArgument(activeView))}
    {#if preset}
      {#key preset.id}
        <LazyView name="presetBuilder" props={{ preset, onnavigate: (v) => onnavigate(v) }} />
      {/key}
    {:else}
      <p class="text-muma-spotify-text p-12 text-center">{$presets.length === 0 && $mumaUser ? $t('common.loading') : $t('presets.notFound')}</p>
    {/if}
  {:else if activeView.startsWith('preset:')}
    {@const preset = $presets.find((p) => p.id === viewArgument(activeView))}
    {#if preset}
      <LazyView name="presetPage" props={{ preset, onnavigate: (v) => onnavigate(v) }} />
    {:else}
      <p class="text-muma-spotify-text p-12 text-center">{$presets.length === 0 && $mumaUser ? $t('common.loading') : $t('presets.notFound')}</p>
    {/if}
  {:else if activeView === 'wrapped' || activeView.startsWith('wrapped:')}
    <LazyView name="wrapped" props={{ route: activeView === 'wrapped' ? '' : viewArgument(activeView), onnavigate: (v) => onnavigate(v) }} />
  {:else if activeView === 'memories'}
    <LazyView name="memories" props={{ onnavigate: (v) => onnavigate(v) }} />
  {:else if activeView.startsWith('memories:')}
    <LazyView name="memoriesYear" props={{ year: viewArgument(activeView), onnavigate: (v) => onnavigate(v) }} />
  {:else if activeView === 'voice'}
    <LazyView name="voice" />
  {/if}
</div>

<style>
</style>
