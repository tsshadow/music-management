<script>
  import { t } from './i18n/index.js';
  import { fetchGenreTints, withTints } from './genreTints.js';
  import { Pencil } from '@lucide/svelte';
  import { untrack } from 'svelte';
  import { SvelteMap } from 'svelte/reactivity';
  import TrackCard from './TrackCard.svelte';
  import TrackList from './TrackList.svelte';
  import FilterBar from './FilterBar.svelte';
  import PlaylistView from './PlaylistView.svelte';
  import ArtistView from './ArtistView.svelte';
  import AlbumView from './AlbumView.svelte';
  import SongView from './SongView.svelte';
  import ArtistList from './ArtistList.svelte';
  import Settings from './Settings.svelte';
  import History from './History.svelte';
  import ListeningStatsView from './ListeningStatsView.svelte';
  import StarredView from './StarredView.svelte';
  import MemoriesView from './MemoriesView.svelte';
  import FeedView from './FeedView.svelte';
  import MemoriesYearView from './MemoriesYearView.svelte';
  import ArtistEdit from './curation/ArtistEdit.svelte';
  import LabelEdit from './curation/LabelEdit.svelte';
  import GenreEdit from './curation/GenreEdit.svelte';
  import Management from './management/Management.svelte';
  import CollectionBar from './CollectionBar.svelte';
  import CollectionGrid from './CollectionGrid.svelte';
  import DownloadsView from './DownloadsView.svelte';
  import OfflineNotice from './OfflineNotice.svelte';
  import { listOf, offline, subsonicJson, viewHasOfflineSource } from './subsonic.js';
  import { getArtistImageUrl, viewArgument } from './utils.js';
  import { localDateString, memoryCount, memoryHeading, parseMemoryGroups } from './memories.js';
  import { deduplicateTracks, getDeduplicateKey } from './deduplicate.js';
  import { defaultCollectionState, durationParts, lineupLevel, queryCollection, PLAYLIST_VISIBILITY } from './collections.js';
  import { loadIndexedTags } from './scanTags.js';
  import { loadFeed, DAILY_MIX, RELEASE_RADAR } from './feeds.js';
  import { authParams, credentials, currentPlaylist, viewMode, favoriteGenres, favoriteLabels, favoritePlaylists, deduplicateEnabled, memoriesOnHomeEnabled, trackPageSize, hasPermission, restUrl } from './store.js';

  // Navigation that has to survive a refresh goes through onnavigate, which App turns into a URL.
  // The local assignment stays the fallback for the many places that only switch the screen.
  let { activeView = $bindable('home'), onnavigate = (view) => (activeView = view) } = $props();

  // The first two are MuMa's personalized feeds; the rest are LMS's own curated lists.
  //
  // The row that used to sit at the top was `spotify:release_radar`, which is the whole library
  // under ten minutes sorted by release date -- the same list for every listener, personalized in
  // name only. The real radar knows what this account plays, so it takes the name and the place.
  let sections = $state([
    { titleKey: 'nav.dailyMix', id: `feed:${DAILY_MIX}`, tracks: [] },
    { titleKey: 'nav.releaseRadar', id: `feed:${RELEASE_RADAR}`, tracks: [] },
    { titleKey: 'nav.songs', id: 'spotify:songs', tracks: [] },
    { titleKey: 'nav.sets', id: 'spotify:sets', tracks: [] }
  ]);

  /** How much of a feed a home row shows. The whole thing lives on the feed's own page. */
  const HOME_FEED_ROWS = 10;

  let memoryGroups = $state([]);

  // The carousel is a teaser, not the whole feature: it stays a short strip whatever the day holds.
  const MEMORY_CARDS = 10;

  let tracks = $state([]);
  let albums = $state([]);
  let artists = $state([]);
  let allGenres = $state([]);
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

  const visibleGenres = $derived(queryCollection(allGenres, 'genres', genreView, { favorites: $favoriteGenres }));
  const visibleLabels = $derived(queryCollection(allLabels, 'labels', labelView, { favorites: $favoriteLabels }));
  const visiblePodcasts = $derived(queryCollection(allPodcasts, 'podcasts', podcastView));
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

  let isLoading = $state(false);
  let seenKeys = new SvelteMap();

  let tracksController;
  let albumsController;
  let artistsController;

  /**
   * Fetches tracks for a specific curated playlist.
   *
   * @param {string} id - The Subsonic ID of the curated playlist.
   * @returns {Promise<Object[]>} A promise that resolves to an array of tracks.
   */
  async function fetchTracks(id) {
    if (!$authParams) return [];

    // A personalized feed is two calls against two services, not one Subsonic playlist.
    if (id.startsWith('feed:')) {
      return loadFeed(id.slice('feed:'.length), $authParams, HOME_FEED_ROWS);
    }

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
   * Loads tracks for the 'songs', 'sets', or 'genre' views with pagination.
   *
   * @param {boolean} [append=false] - Whether to append new results to the existing tracks.
   */
  async function loadAllTracks(append = false) {
    if (!$authParams) return;
    if (!append) {
      tracksOffset = 0;
      tracksHasMore = true;
      seenKeys = new SvelteMap();
      if (tracksController) {
        tracksController.abort();
      }
      tracksController = new AbortController();
    }
    if (!tracksHasMore) return;

    const signal = tracksController?.signal;

    console.log(`Loading all tracks, activeView=${activeView}, genre=${currentGenre}, sort=${currentSort}, year=${currentYear}, minRating=${currentMinRating}, offset=${tracksOffset}`);
    isLoading = true;

    let currentBatch = [];
    try {
      while (currentBatch.length < pageSize && tracksHasMore) {
        const argument = viewArgument(activeView);
        const params = {
          sort: currentSort,
          offset: tracksOffset,
          count: pageSize,
          seed: currentSort === 'random' ? currentSeed : undefined,
          deduplicate: $deduplicateEnabled ? 'true' : undefined,
          query: currentTrackSearch || undefined,
          genre: currentGenre || (activeView.startsWith('genre:') ? argument : undefined),
          label: activeView.startsWith('label:') ? argument : undefined,
          podcast: activeView.startsWith('podcast:') ? argument : undefined,
          festival: activeView.startsWith('festival:') ? argument : undefined,
          lineup: activeView.startsWith('lineup:') ? argument : undefined,
          // The year view reuses the parameter the filter bar already drives. Seeding
          // `currentYear` from the route instead would not survive: resetTrackFiltersFor
          // clears it on every arrival at a new track view, before the first fetch.
          year: currentYear || (activeView.startsWith('year:') ? argument : undefined),
          minRating: currentMinRating !== '0' ? currentMinRating : undefined,
          includeUnrated: includeUnrated ? 'true' : undefined,
          // Minutes on this endpoint, not seconds; the offline library reads them
          // the same way. Ten is the songs/sets boundary the whole app uses.
          ...($viewMode === 'sets' ? { minDuration: 10 } : { maxDuration: 10 })
        };

        const data = await subsonicJson('getSpotifyTracks', params, { signal });
        const tracksNode = data['subsonic-response']?.tracks;
        const newTracks = listOf(data, 'tracks.track');

        // Deduplicate this batch against what we've seen before if enabled
        const deduped = $deduplicateEnabled ? deduplicateTracks(newTracks, seenKeys) : newTracks;

        // Update seenKeys for the tracks we are actually going to show
        if ($deduplicateEnabled) {
          for (const track of deduped) {
            seenKeys.set(getDeduplicateKey(track), track);
          }
        }

        currentBatch.push(...deduped);
        
        const moreResults = tracksNode?.moreResults;
        tracksHasMore = moreResults !== undefined ? (String(moreResults) === 'true' || moreResults === true) : newTracks.length === pageSize;
        tracksOffset = tracksNode?.nextOffset !== undefined ? tracksNode.nextOffset : (tracksOffset + newTracks.length);

        console.log(`Fetched ${newTracks.length} tracks, ${deduped.length} unique in this batch. Total unique in batch: ${currentBatch.length}. tracksHasMore: ${tracksHasMore}, nextOffset: ${tracksOffset}`);

        if (!tracksHasMore || currentBatch.length >= pageSize) break;
      }

      if (append) {
        tracks = [...tracks, ...currentBatch];
      } else {
        tracks = currentBatch;
      }
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.error("Failed to load tracks:", e);
    } finally {
      if (!signal || !signal.aborted) {
        isLoading = false;
      }
    }
  }

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
    }
  }

  /**
   * Loads all user playlists from the server.
   */
  async function loadPlaylists() {
    if (!$authParams) return;
    try {
      const response = await fetch(restUrl(`/rest/getPlaylists?${$authParams}`));
      const data = await response.json();
      playlists = data['subsonic-response']?.playlists?.playlist || [];
    } catch (e) { console.error(e); }
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
      const { genre, sort, year, search, role, minRating, includeUnrated: incUnrated } = params;
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
          loadAllTracks();
      }
  }

  /**
   * Loads all curated sections (Release Radar, Songs, Sets) for the home view.
   */
  async function loadCurated() {
    const results = await Promise.all(sections.map(section => fetchTracks(section.id)));
    sections = sections.map((section, index) => {
      section.tracks = results[index];
      return section;
    });
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

  $effect(() => {
    const view = activeView;
    const auth = $authParams;
    const mode = $viewMode;
    // A dependency on purpose: coming back online has to re-run the loader for
    // the view the listener is already standing on.
    const unreachable = $offline && !viewHasOfflineSource(view);

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
            loadAllTracks();
            loadAlbums();
            loadArtists();
        }
      });
    }
  });

  $effect(() => {
    if (sentinel && tracksHasMore && !isLoading && (activeView === 'songs' || activeView === 'sets' || activeView.startsWith('genre:') || activeView.startsWith('label:') || activeView.startsWith('podcast:') || activeView.startsWith('festival:') || activeView.startsWith('year:') || activeView.startsWith('lineup:') || activeView.startsWith('search:'))) {
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
  <div class="text-[#b3b3b3] p-12 text-center border border-white/5 rounded-xl bg-white/5">
    <p class="text-xl font-bold mb-2 text-white">{$t('collection.noMatches')}</p>
    <p class="text-sm opacity-60 mb-4">{$t('collection.noMatchesHelp')}</p>
    <button
      class="bg-transparent border border-[#727272] text-white px-6 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]"
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
    <DownloadsView onnavigate={onnavigate} />
  {:else if activeView === 'home'}
    {#if $memoriesOnHomeEnabled && memoryGroups.length > 0}
      <section class="flex flex-col gap-4">
        <div class="flex justify-between items-end mb-4">
          <h2 class="text-2xl font-bold m-0">{$t('memories.title')}</h2>
          <button
            class="bg-transparent border-none text-[#b3b3b3] text-[12px] font-bold cursor-pointer uppercase tracking-[0.1em] hover:underline"
            onclick={() => onnavigate('memories')}
          >{$t('dashboard.showAll')}</button>
        </div>
        <div class="flex gap-4 overflow-x-auto pb-2">
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
              <div class="text-[#b3b3b3] text-xs">
                {group.year} • {$t('common.trackCount', { count: memoryCount(group) })}
              </div>
            </button>
          {/each}
        </div>
      </section>
    {/if}
    {#each sections.filter((s) => !s.id.startsWith('feed:') || s.tracks.length > 0) as section (section.id)}
      <section class="flex flex-col gap-4">
        <div class="flex justify-between items-end mb-4">
          <h2 class="text-2xl font-bold m-0">{$t(section.titleKey)}</h2>
          <button
            class="bg-transparent border-none text-[#b3b3b3] text-[12px] font-bold cursor-pointer uppercase tracking-[0.1em] hover:underline"
            onclick={() => {
              if (section.id.startsWith('feed:')) {
                onnavigate(section.id.slice('feed:'.length));
              } else if (section.id === 'spotify:songs') {
                viewMode.set('songs');
                activeView = 'songs';
              } else if (section.id === 'spotify:sets') {
                viewMode.set('sets');
                activeView = 'sets';
              }
            }}
          >{$t('dashboard.showAll')}</button>
        </div>
        <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
          {#each section.tracks.slice(0, 6) as track (track.id)}
            <TrackCard {track} onnavigate={(v) => activeView = v} />
          {/each}
          {#if section.tracks.length === 0}
            <p class="text-[#b3b3b3] col-span-full">{$t('dashboard.noTracksInSection')}</p>
          {/if}
        </div>
      </section>
    {/each}
  {:else if activeView === 'songs' || activeView === 'sets' || activeView.startsWith('genre:') || activeView.startsWith('label:') || activeView.startsWith('podcast:') || activeView.startsWith('festival:') || activeView.startsWith('year:') || activeView.startsWith('lineup:')}
    <div class="flex flex-col gap-4 mb-6">
        <h2 class="text-2xl font-bold m-0 flex items-center gap-3">
            {#if activeView === 'songs' || activeView === 'sets'}
              {$viewMode === 'sets' ? 'Sets' : 'Alle Nummers'}
            {:else if activeView.startsWith('genre:')}
              {@const genreName = viewArgument(activeView)}
              <span>{genreName}</span>
              {#if hasPermission('rules.manage')}
                <button
                  class="bg-transparent border-none text-[#b3b3b3] hover:text-white transition-all hover:scale-110 cursor-pointer p-1"
                  onclick={() => activeView = `genre-edit:${genreName}`}
                  title="Genre bewerken"
                  aria-label="Genre bewerken"
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
                  class="bg-transparent border-none text-[#b3b3b3] hover:text-white transition-all hover:scale-110 cursor-pointer p-1"
                  onclick={() => activeView = `label-edit:${collectionName}`}
                  title="Label bewerken"
                  aria-label="Label bewerken"
                >
                  <Pencil size={20} />
                </button>
              {/if}
            {/if}
        </h2>
        <FilterBar view="songs" bind:genre={currentGenre} bind:sort={currentSort} bind:year={currentYear} bind:search={currentTrackSearch} bind:minRating={currentMinRating} bind:includeUnrated={includeUnrated} showGenre={!activeView.startsWith('genre:') && !activeView.startsWith('label:') && !activeView.startsWith('podcast:')} showYear={!activeView.startsWith('year:')} onchange={handleFilterChange} />
    </div>
    {#if isLoading && tracks.length === 0}
        <p>{$t('common.loading')}</p>
    {:else}
        {#if tracks.length > 0}
            <TrackList {tracks} onnavigate={(v) => activeView = v} />
            {#if tracksHasMore}
                <div bind:this={sentinel} class="flex justify-center py-6">
                    <button class="bg-transparent border border-[#727272] text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]" onclick={() => loadAllTracks(true)}>
                        {isLoading ? $t('common.loading') : $t('common.loadMore')}
                    </button>
                </div>
            {/if}
        {:else if $offline}
            <!-- The list is empty and there is no connection, so the reason is
                 that nothing here is downloaded -- not that the library is empty. -->
            <OfflineNotice kind="empty" onnavigate={onnavigate} />
        {:else}
            <div class="text-[#b3b3b3] p-12 text-center border border-white/5 rounded-xl bg-white/5">
                <p class="text-xl font-bold mb-2 text-white">{$viewMode === 'sets' ? $t('dashboard.noSets') : $t('dashboard.noTracks')}</p>
                <p class="text-sm opacity-60">{$viewMode === 'sets' ? $t('dashboard.noSetsHelp') : $t('dashboard.noTracksHelp')}</p>
            </div>
        {/if}
    {/if}
  {:else if activeView === 'albums'}
    <div class="flex flex-col gap-4 mb-6">
      <h2 class="text-2xl font-bold m-0">{$t('nav.albums')}</h2>
      <FilterBar view="albums" bind:genre={currentAlbumGenre} bind:sort={currentAlbumSort} bind:search={currentAlbumSearch} onchange={handleFilterChange} />
    </div>
    {#if albums.length > 0}
        <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
            {#each albums as album (album.id)}
                <div
                  role="button"
                  tabindex="0"
                  class="bg-[#181818] p-4 rounded-lg flex flex-col gap-3 cursor-pointer transition-colors hover:bg-[#282828]"
                  onclick={() => activeView = `album:${album.id}`}
                  onkeydown={(e) => e.key === 'Enter' && (activeView = `album:${album.id}`)}
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
        <div class="text-[#b3b3b3] p-12 text-center border border-white/5 rounded-xl bg-white/5">
            <p class="text-xl font-bold mb-2 text-white">{$t('dashboard.noAlbums')}</p>
            <p class="text-sm opacity-60">{$t('dashboard.noAlbumsHelp')}</p>
        </div>
    {/if}
    {#if albumsHasMore}
        <div class="flex justify-center py-6">
            <button class="bg-transparent border border-[#727272] text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]" onclick={() => loadAlbums(true)}>{$t('common.loadMore')}</button>
        </div>
    {/if}
  {:else if activeView === 'genres'}
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
    />
  {:else if activeView === 'podcasts'}
    <CollectionGrid
      type="podcasts"
      title={$t('nav.podcasts')}
      items={allPodcasts}
      bind:state={podcastView}
      loading={isLoading}
      emptyText={$t('collection.noPodcasts')}
      onselect={(item) => (activeView = `podcast:${item.value}`)}
    />
  {:else if activeView === 'labels'}
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
    />
  {:else if activeView === 'festivals'}
    <CollectionGrid
      type="festivals"
      title={$t('nav.festivals')}
      items={allFestivals}
      bind:state={festivalView}
      loading={isLoading}
      emptyText={$t('collection.noFestivals')}
      emptyHint={tagHint('FESTIVAL')}
      onselect={(item) => (activeView = `festival:${item.value}`)}
    />
  {:else if activeView === 'years'}
    <CollectionGrid
      type="years"
      title={$t('nav.years')}
      items={allYears}
      bind:state={yearView}
      loading={isLoading}
      emptyText={$t('collection.noYears')}
      emptyHint={tagHint('YEAR')}
      onselect={(item) => (activeView = `year:${item.value}`)}
    />
  {:else if activeView === 'lineups' || activeView.startsWith('lineups:')}
    {#if lineupCrumbs.length > 0}
      <nav class="flex flex-wrap items-center gap-2 text-sm text-[#b3b3b3] mb-4" aria-label={$t('nav.lineups')}>
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
    <CollectionGrid
      type="lineups"
      title={lineupCrumbs.length > 0 ? lineupCrumbs[lineupCrumbs.length - 1].label : $t('nav.lineups')}
      items={lineupEntries}
      bind:state={lineupView}
      loading={isLoading}
      emptyText={$t('collection.noLineups')}
      emptyHint={$t('collection.noLineupsHelp')}
      onselect={openLineupEntry}
    />
  {:else if activeView === 'artists'}
    <div class="flex flex-col gap-4 mb-6">
      <h2 class="text-2xl font-bold m-0">{$t('nav.artists')}</h2>
      <FilterBar view="artists" bind:sort={currentArtistSort} bind:role={currentArtistRole} bind:search={currentArtistSearch} onchange={handleFilterChange} />
    </div>
    <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
        {#each artists as artist (artist.id)}
            <div
              role="button"
              tabindex="0"
              class="bg-[#181818] p-4 rounded-lg flex flex-col gap-3 cursor-pointer transition-colors hover:bg-[#282828]"
              onclick={() => activeView = `artist:${artist.id}`}
              onkeydown={(e) => e.key === 'Enter' && (activeView = `artist:${artist.id}`)}
            >
                <img
                  src={getArtistImageUrl(artist, $authParams)}
                  alt={artist.name}
                  class="w-full aspect-square object-cover rounded-full shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                  onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
                />
                <span class="font-bold whitespace-nowrap overflow-hidden text-ellipsis">{artist.name}</span>
                <span class="text-sm text-[#b3b3b3] whitespace-nowrap overflow-hidden text-ellipsis">{$t('common.artist')}</span>
            </div>
        {/each}
    </div>
    {#if artistsHasMore}
        <div class="flex justify-center py-6">
            <button class="bg-transparent border border-[#727272] text-white px-8 py-2 rounded-[24px] font-bold cursor-pointer transition-all hover:border-white hover:scale-[1.04]" onclick={() => loadArtists(true)}>{$t('common.loadMore')}</button>
        </div>
    {/if}
  {:else if activeView === 'playlists'}
    <div class="flex flex-col gap-4 mb-6">
      <h2 class="text-2xl font-bold m-0">{$t('nav.playlists')}</h2>
      <CollectionBar
        type="playlists"
        bind:state={playlistView}
        total={playlists.length}
        shown={visiblePlaylists.length}
        favoriteCount={$favoritePlaylists.length}
        visibilityOptions={PLAYLIST_VISIBILITY}
      />
    </div>
    {#if playlists.length === 0}
        <div class="text-[#b3b3b3] p-12 text-center border border-white/5 rounded-xl bg-white/5">
            <p class="text-xl font-bold mb-2 text-white">{$t('dashboard.noPlaylists')}</p>
            <p class="text-sm opacity-60">{$t('dashboard.noPlaylistsHelp')}</p>
        </div>
    {:else if visiblePlaylists.length === 0}
        {@render noMatches(() => (playlistView = defaultCollectionState('playlists')))}
    {:else}
    <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
        {#each visiblePlaylists as playlist (playlist.id)}
            <div
              role="button"
              tabindex="0"
              class="bg-[#181818] p-4 rounded-lg flex flex-col gap-3 cursor-pointer transition-colors hover:bg-[#282828] relative group"
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
                <span class="text-xs text-[#b3b3b3] whitespace-nowrap overflow-hidden text-ellipsis">
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
    <PlaylistView onnavigate={(v) => activeView = v} />
  {:else if activeView.startsWith('artist-edit:')}
    <ArtistEdit artistId={viewArgument(activeView)} onback={() => activeView = `artist:${viewArgument(activeView)}`} />
  {:else if activeView.startsWith('label-edit:')}
    <LabelEdit name={viewArgument(activeView)} onback={() => activeView = `label:${viewArgument(activeView)}`} />
  {:else if activeView.startsWith('genre-edit:')}
    <GenreEdit name={viewArgument(activeView)} onback={() => activeView = `genre:${viewArgument(activeView)}`} />
  {:else if activeView.startsWith('artist:')}
    <ArtistView artistId={viewArgument(activeView)} onnavigate={(v) => activeView = v} />
  {:else if activeView.startsWith('album:')}
    <AlbumView albumId={viewArgument(activeView)} onnavigate={(v) => activeView = v} />
  {:else if activeView.startsWith('song:')}
    <SongView workId={viewArgument(activeView)} onnavigate={(v) => activeView = v} />
  {:else if activeView.startsWith('search:')}
    <div class="flex flex-col gap-8">
      <h2 class="text-2xl font-bold m-0">{$viewMode === 'sets' ? $t('dashboard.searchResultsSets', { query: viewArgument(activeView) }) : $t('dashboard.searchResultsTracks', { query: viewArgument(activeView) })}</h2>
      
      {#if tracks.length > 0}
        <section>
          <h3 class="text-xl font-bold mb-4">{$viewMode === 'sets' ? 'Sets' : 'Nummers'}</h3>
          <TrackList {tracks} onnavigate={(v) => activeView = v} />
        </section>
      {/if}

      {#if artists.length > 0}
        <section>
          <h3 class="text-xl font-bold mb-4">{$t('nav.artists')}</h3>
          <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
            {#each artists as artist (artist.id)}
              <div
                role="button"
                tabindex="0"
                class="bg-[#181818] p-4 rounded-lg flex flex-col gap-3 cursor-pointer transition-colors hover:bg-[#282828]"
                onclick={() => activeView = `artist:${artist.id}`}
                onkeydown={(e) => e.key === 'Enter' && (activeView = `artist:${artist.id}`)}
              >
                  <img
                    src={getArtistImageUrl(artist, $authParams)}
                    alt={artist.name}
                    class="w-full aspect-square object-cover rounded-full shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                    onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
                  />
                  <span class="font-bold whitespace-nowrap overflow-hidden text-ellipsis">{artist.name}</span>
                  <span class="text-sm text-[#b3b3b3]">{$t('common.artist')}</span>
              </div>
            {/each}
          </div>
        </section>
      {/if}

      {#if albums.length > 0}
        <section>
          <h3 class="text-xl font-bold mb-4">{$t('nav.albums')}</h3>
          <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
            {#each albums as album (album.id)}
              <div
                role="button"
                tabindex="0"
                class="bg-[#181818] p-4 rounded-lg flex flex-col gap-3 cursor-pointer transition-colors hover:bg-[#282828]"
                onclick={() => activeView = `album:${album.id}`}
                onkeydown={(e) => e.key === 'Enter' && (activeView = `album:${album.id}`)}
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
        </section>
      {/if}

      {#if tracks.length === 0 && artists.length === 0 && albums.length === 0}
        {#if $offline}
          <!-- Search does reach the device; finding nothing there means nothing
               matching is downloaded, which is not "try another term". -->
          <OfflineNotice kind="empty" onnavigate={onnavigate} />
        {:else}
          <div class="text-[#b3b3b3] p-12 text-center border border-white/5 rounded-xl bg-white/5">
              <p class="text-xl font-bold mb-2 text-white">{$t('search.noResults')}</p>
              <p class="text-sm opacity-60">{$t('search.tryAnother')}</p>
          </div>
        {/if}
      {/if}
    </div>
  {:else if activeView === 'settings'}
    <Settings />
  {:else if activeView === 'management'}
    <Management />
  {:else if activeView === 'history'}
    <History onnavigate={(v) => activeView = v} />
  {:else if activeView === 'listening'}
    <ListeningStatsView onnavigate={(v) => onnavigate(v)} />
  {:else if activeView === 'starred'}
    <StarredView onnavigate={(v) => activeView = v} />
  {:else if activeView === 'release-radar'}
    <FeedView slug={RELEASE_RADAR} onnavigate={(v) => onnavigate(v)} />
  {:else if activeView === 'daily-mix'}
    <FeedView slug={DAILY_MIX} onnavigate={(v) => onnavigate(v)} />
  {:else if activeView === 'memories'}
    <MemoriesView onnavigate={(v) => onnavigate(v)} />
  {:else if activeView.startsWith('memories:')}
    <MemoriesYearView year={viewArgument(activeView)} onnavigate={(v) => onnavigate(v)} />
  {/if}
</div>

<style>
</style>
