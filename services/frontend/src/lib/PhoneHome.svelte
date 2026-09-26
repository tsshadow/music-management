<script>
  import { onMount } from 'svelte';
  import { t } from './i18n/index.js';
  import { authParams, restUrl, viewMode, mumaApiKey, memoriesOnHomeEnabled, homeModeReleaseRadar, homeModeDailyMix,
    homeModeFavorites, homeModeRecentlyReleased, homeModeRecentlyAdded } from './store.js';
  import { memoryCount, playMemoryYear, yearTiles } from './memories.js';
  import { listOf, subsonicJson } from './subsonic.js';
  import { loadTopArtists, loadTopLabels, resolveArtistView } from './homeRankings.js';
  import { TILE_COLORS as BROWSE_TILE_COLORS } from './browseColors.js';
  import QuickAccessTile from './QuickAccessTile.svelte';
  import HomeShelf from './HomeShelf.svelte';
  import DailyMixesShelf from './DailyMixesShelf.svelte';
  import MemoryYearCard from './MemoryYearCard.svelte';

  /** Phone home maps the account's section modes to tiles or shelves over its own sources. */
  const { memoryGroups = [], onnavigate, onrecent = null } = $props();

  /**
   * Colour and icon per quick-access tile. `memories` and `starred` share the id (and
   * therefore the colour) `BrowseGrid.svelte` uses for the same destination, so the tile
   * looks the same whether it was reached from Home or from Bladeren; the icons for those
   * two are `BrowseGrid`'s icons too (a clock face, a heart). The other tiles have no
   * Browse equivalent, so they get their own colour from the same palette and a fitting
   * Material icon: a mic for the "radar" scan, a shuffle glyph for the mix, a calendar for
   * release dates, a download arrow for library additions.
   */
  const TILE_COLORS = {
    memories: '#503750',
    'release-radar': '#0D73EC',
    'daily-mixes': '#2D5AFC',
    starred: '#E8115B',
    'recently-released': '#1E3264',
    'recently-added': '#148A08',
  };
  const TILE_ICONS = {
    memories: 'M11.99 2C6.47 2 2 6.48 2 12s4.47 10 9.99 10C17.52 22 22 17.52 22 12S17.52 2 11.99 2zM12 20c-4.42 0-8-3.58-8-8s3.58-8 8-8 8 3.58 8 8-3.58 8-8 8zm.5-13H11v6l5.25 3.15.75-1.23-4.5-2.67z',
    'release-radar': 'M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5-3c0 2.76-2.24 5-5 5s-5-2.24-5-5H5c0 3.53 2.61 6.43 6 6.92V21h2v-2.08c3.39-.49 6-3.39 6-6.92h-2z',
    'daily-mixes': 'M10.59 9.17L5.41 4 4 5.41l5.17 5.17 1.42-1.41zM14.5 4l2.04 2.04L4 18.59 5.41 20 17.96 7.46 20 9.5V4h-5.5zm.33 9.41l-1.41 1.41 3.13 3.13L14.5 20H20v-5.5l-2.04 2.04-3.13-3.13z',
    starred: 'M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z',
    'recently-released': 'M19 4h-1V2h-2v2H8V2H6v2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 16H5V10h14v10zM5 8V6h14v2H5z',
    'recently-added': 'M12 16l6-6h-4V2h-4v8H6l6 6zM4 18v4h16v-4H4z',
  };
  /**
   * The i18n key for a destination's designed empty copy, keyed the same way `TILE_COLORS`
   * and `TILE_ICONS` are. A generic "no tracks in this category" line reads as broken on a
   * tile that is *always* pointing at a real place -- Release Radar has no tracks until MuMa
   * has a taste profile, Favourites has none until something is starred -- so each of the four
   * gets a line that explains what the tile is for instead.
   */
  const EMPTY_COPY_KEYS = {
    'release-radar': 'dashboard.empty.releaseRadar',
    starred: 'dashboard.empty.starred',
    'recently-released': 'dashboard.empty.recentlyReleased',
    'recently-added': 'dashboard.empty.recentlyAdded',
  };

  /** An ellipsis, not a translated string: "still loading" needs no wording, in any language. */
  const LOADING_SUBTITLE = '…';

  let favorites = $state([]);
  let favoritesState = $state('loading');
  // Home's two ranking strips ("Jouw artiesten deze maand", "Jouw labels"); empty until the
  // account has a MuMa API key and the load below resolves, which is also what keeps both
  // strips hidden -- there is nothing to distinguish "not loaded yet" from "no listens" for
  // a row this far down the page, and both read fine as simply absent.
  let topArtists = $state([]);
  let topLabels = $state([]);
  let recentlyReleased = $state([]);
  let recentlyReleasedState = $state('loading');
  let recentlyAdded = $state([]);
  let recentlyAddedState = $state('loading');
  const destinations = $derived([
    // The two personalised feeds are not track lists on Home -- each is a card (or a tile) that
    // opens its own page, and no tracks are fetched for either until then. `kind: 'feed'` is what
    // routes them to DailyMixesShelf below instead of a HomeShelf of tracks.
    { id: 'release-radar', kind: 'feed', key: 'nav.releaseRadar', mode: $homeModeReleaseRadar, tracks: [], state: 'ready' },
    { id: 'daily-mixes', kind: 'feed', key: 'nav.dailyMixes', mode: $homeModeDailyMix },
    { id: 'starred', key: 'nav.starred', mode: $homeModeFavorites, tracks: favorites, state: favoritesState },
    { id: 'recently-released', sort: 'recent', view: $viewMode, key: 'settings.general.home.recentlyReleased', mode: $homeModeRecentlyReleased, tracks: recentlyReleased, state: recentlyReleasedState },
    { id: 'recently-added', sort: 'added', view: $viewMode, key: 'settings.general.home.recentlyAdded', mode: $homeModeRecentlyAdded, tracks: recentlyAdded, state: recentlyAddedState },
  ]);
  // SHORTCUTS has no recent-places store in the web UI. Its saved mode intentionally renders nothing.

  /** The Memories year row's tiles: one per year with songs, the same shape the Memories grid uses. */
  const memoryTiles = $derived(yearTiles(memoryGroups));

  /**
   * Home's fallback "something to play" shelf. When both `recently-added` and `recently-released`
   * are BUTTON or OFF, neither renders as its own OVERVIEW shelf above, and Home would show nothing
   * below the shortcuts; this picks the one destination matching the current view mode instead, so
   * the screen never ends at the tile grid. Never used when the matching destination is already an
   * OVERVIEW shelf, so it is never drawn twice.
   */
  const fallbackRecentSection = $derived.by(() => {
    const added = destinations.find(section => section.id === 'recently-added');
    const released = destinations.find(section => section.id === 'recently-released');
    if (added?.mode === 'OVERVIEW' || released?.mode === 'OVERVIEW') return null;
    return $viewMode === 'sets' ? released : added;
  });

  /**
   * The quick-access tiles, in render order: the memories tile (when enabled) first, then
   * every BUTTON-mode destination. A single list rather than the two separate template blocks
   * this used to be, because giving the *last* tile `col-span-2` on an odd count needs one
   * combined index -- otherwise a lone memories tile and a lone destination tile would each
   * think they were "the last of one" and both stretch.
   */
  const tiles = $derived([
    ...($memoriesOnHomeEnabled ? [{ id: 'memories', kind: 'memories' }] : []),
    ...destinations.filter(section => section.mode === 'BUTTON'),
  ]);

  /** Opening a recent shelf keeps its ordering in the full track list. */
  function openSection(section) {
    if (section.sort && onrecent) onrecent(section.sort);
    else onnavigate(section.view ?? section.id);
  }

  /**
   * The one card row for whichever of the two feeds the account shows as "Overzicht", rendered
   * in the slot of the first of them so the two never become two rows of cards. `null` when
   * neither is an overview.
   */
  const feedOverview = $derived.by(() => {
    const overview = destinations.filter(section => section.kind === 'feed' && section.mode === 'OVERVIEW');
    if (overview.length === 0) return null;
    return {
      at: overview[0].id,
      radar: overview.some(section => section.id === 'release-radar'),
      mixes: overview.some(section => section.id === 'daily-mixes'),
    };
  });

  /**
   * The line under a tile's title. A feed's home copy is capped (`HOME_FEED_ROWS` in
   * Dashboard) and the recent lists ask for six, so a count there would read "10 nummers"
   * on every tile whatever the feed holds; the first track says something true instead.
   * Favourites is the one list fetched whole, so its count is real.
   *
   * A failed load and a still-loading one both take priority over that: neither has a
   * meaningful first track to describe, and both need to look different from "empty" -- a
   * source stuck on the designed empty copy forever would never announce it had failed.
   *
   * @param {object} section
   * @returns {string}
   */
  function subtitle(section) {
    if (section.state === 'failed') return $t('dashboard.loadFailed');
    if (section.state === 'loading') return LOADING_SUBTITLE;
    if (section.tracks.length === 0) return $t(EMPTY_COPY_KEYS[section.id] ?? 'dashboard.noTracksInSection');
    if (section.id === 'starred') return $t('common.trackCount', { count: section.tracks.length });
    const first = section.tracks[0];
    return first.artist ? `${first.artist} – ${first.title}` : first.title;
  }

  /** Artwork stays optional so empty feeds still have a useful navigation tile. */
  function cover(track) {
    return track?.coverArt ? restUrl(`/rest/getCoverArt?id=${track.coverArt}&size=100&${$authParams}`) : null;
  }

  // The curated songs/sets are random. Ask the existing track endpoint for real release/add
  // order instead, using the same ten-minute boundary as Dashboard's full track lists.
  $effect(() => {
    const duration = $viewMode === 'sets' ? { minDuration: 10 } : { maxDuration: 10 };
    if (!$authParams) {
      recentlyReleasedState = 'ready';
      recentlyAddedState = 'ready';
      return;
    }
    let stale = false;
    // A mode switch reruns this; the tiles must pulse again rather than keep
    // showing the previous mode's "could not load" until the new answer lands.
    recentlyReleasedState = 'loading';
    recentlyAddedState = 'loading';
    /** One of the two lists, tagged with whether it actually arrived. */
    function loadRecent(sort) {
      return subsonicJson('getSpotifyTracks', { sort, count: 6, offset: 0, deduplicate: 'true', ...duration })
        .then(data => ({ tracks: listOf(data, 'tracks.track'), state: 'ready' }))
        .catch(error => {
          console.warn('Could not load recent home tracks', sort, error);
          return { tracks: [], state: 'failed' };
        });
    }
    Promise.all([loadRecent('recent'), loadRecent('added')]).then(([released, added]) => {
      if (stale) return;
      recentlyReleased = released.tracks;
      recentlyReleasedState = released.state;
      recentlyAdded = added.tracks;
      recentlyAddedState = added.state;
    });
    return () => { stale = true; };
  });

  onMount(async () => {
    if (!$authParams) { favoritesState = 'ready'; return; }
    try {
      favorites = listOf(await subsonicJson('getStarred2'), 'starred2.song');
      favoritesState = 'ready';
    } catch (error) {
      console.warn('Could not load home favourites', error);
      favoritesState = 'failed';
    }
  });

  // The listening endpoints need the MuMa key, not the Subsonic credentials `$authParams`
  // gates on above -- an account can have one without the other -- so this loads once on
  // mount, only when that key is present, and never retries on its own; `stale` only
  // matters for the (test-only, in practice) case of the component unmounting mid-request.
  onMount(() => {
    if (!$mumaApiKey) return;
    let stale = false;
    Promise.all([loadTopArtists(), loadTopLabels()]).then(([artists, labels]) => {
      if (stale) return;
      topArtists = artists;
      topLabels = labels;
    });
    return () => { stale = true; };
  });

  /**
   * A tapped artist ranking resolves to the library's LMS artist id first, since the
   * MuMa id the ranking itself carries is not one `onnavigate` can use. A name with no
   * match (an artist MuMa knows only from scrobbles, not the library) still opens
   * somewhere useful: the same search results a manual search for that name would give.
   *
   * @param {string} name
   */
  async function openArtistRanking(name) {
    const view = await resolveArtistView(name);
    onnavigate(view ?? `search:${name}`);
  }
</script>

<div class="grid grid-cols-2 gap-2" data-testid="home-quick-access">
  {#each tiles as tile, index (tile.id)}
    {@const lastOdd = index === tiles.length - 1 && tiles.length % 2 === 1}
    {#if tile.kind === 'memories'}
      <QuickAccessTile title={$t('memories.title')}
        subtitle={$t('memories.homeSummary', { years: memoryGroups.length, tracks: memoryGroups.reduce((count, group) => count + memoryCount(group), 0) })}
        cover={cover(memoryGroups[0]?.songs[0])} color={TILE_COLORS.memories} icon={TILE_ICONS.memories}
        class={lastOdd ? 'col-span-2' : ''}
        onclick={() => onnavigate('memories')} />
    {:else if tile.id === 'daily-mixes'}
      <QuickAccessTile title={$t(tile.key)} subtitle={$t('dashboard.dailyMixesSubtitle')}
        color={TILE_COLORS[tile.id]} icon={TILE_ICONS[tile.id]}
        class={lastOdd ? 'col-span-2' : ''}
        onclick={() => onnavigate('daily-mixes')} />
    {:else}
      <QuickAccessTile title={$t(tile.key)} subtitle={subtitle(tile)}
        cover={cover(tile.tracks[0])} color={TILE_COLORS[tile.id]} icon={TILE_ICONS[tile.id]}
        loading={tile.state === 'loading'} class={lastOdd ? 'col-span-2' : ''}
        onclick={() => openSection(tile)} />
    {/if}
  {/each}
</div>
{#each destinations.filter(section => section.mode === 'OVERVIEW') as section (section.id)}
  {#if section.kind === 'feed'}
    {#if feedOverview?.at === section.id}
      <DailyMixesShelf radar={feedOverview.radar} mixes={feedOverview.mixes} {onnavigate} />
    {/if}
  {:else}
    <HomeShelf title={$t(section.key)} tracks={section.tracks.slice(0, 6)}
      layout={section.id === 'recently-released' || section.id === 'recently-added' ? 'rows' : 'cards'}
      noTracksText={$t(EMPTY_COPY_KEYS[section.id] ?? 'dashboard.noTracksInSection')} showAllLabel={$t('dashboard.showAll')}
      {onnavigate} onshowall={() => openSection(section)} />
  {/if}
{/each}
{#if $memoriesOnHomeEnabled && memoryTiles.length > 0}
  <section class="flex flex-col gap-3" data-testid="home-memories-row">
    <div class="flex justify-between items-end mb-4">
      <h2 class="text-xl font-bold m-0">{$t('memories.title')}</h2>
      <button
        class="bg-transparent border-none text-muma-spotify-text text-[13px] font-bold cursor-pointer hover:underline"
        onclick={() => onnavigate('memories')}
      >{$t('dashboard.showAll')}</button>
    </div>
    <div class="flex gap-3 overflow-x-auto snap-x scrollbar-hide -mx-4 px-4 pb-1">
      {#each memoryTiles as tile (tile.year)}
        <div class="w-[140px] shrink-0">
          <MemoryYearCard {tile}
            onopen={(year) => onnavigate(`memories:${year}`)}
            onplay={(year) => playMemoryYear(year, memoryGroups, $authParams)} />
        </div>
      {/each}
    </div>
  </section>
{/if}
{#if fallbackRecentSection && fallbackRecentSection.tracks.length > 0}
  <HomeShelf title={$t(fallbackRecentSection.key)} tracks={fallbackRecentSection.tracks.slice(0, 6)}
    layout="rows" showAllLabel={$t('dashboard.showAll')}
    {onnavigate} onshowall={() => openSection(fallbackRecentSection)} />
{/if}
{#if topArtists.length > 0}
  <section class="flex flex-col gap-3" data-testid="home-top-artists">
    <div class="flex justify-between items-end mb-4">
      <h2 class="text-xl font-bold m-0">{$t('dashboard.topArtists')}</h2>
      <button
        class="bg-transparent border-none text-muma-spotify-text text-[13px] font-bold cursor-pointer hover:underline"
        onclick={() => onnavigate('listening')}
      >{$t('dashboard.showAll')}</button>
    </div>
    <div class="flex gap-3 overflow-x-auto snap-x scrollbar-hide -mx-4 px-4 pb-1">
      {#each topArtists as artist (artist.name)}
        <QuickAccessTile
          class="w-[150px] shrink-0"
          title={artist.name}
          subtitle={$t('common.listenCount', { count: artist.listens })}
          color={BROWSE_TILE_COLORS.artists}
          onclick={() => openArtistRanking(artist.name)}
        />
      {/each}
    </div>
  </section>
{/if}
{#if topLabels.length > 0}
  <section class="flex flex-col gap-3" data-testid="home-top-labels">
    <div class="flex justify-between items-end mb-4">
      <h2 class="text-xl font-bold m-0">{$t('dashboard.topLabels')}</h2>
      <button
        class="bg-transparent border-none text-muma-spotify-text text-[13px] font-bold cursor-pointer hover:underline"
        onclick={() => onnavigate('listening')}
      >{$t('dashboard.showAll')}</button>
    </div>
    <div class="flex gap-3 overflow-x-auto snap-x scrollbar-hide -mx-4 px-4 pb-1">
      {#each topLabels as label (label.name)}
        <QuickAccessTile
          class="w-[150px] shrink-0"
          title={label.name}
          subtitle={$t('common.listenCount', { count: label.listens })}
          color={BROWSE_TILE_COLORS.labels}
          onclick={() => onnavigate(`label:${label.name}`)}
        />
      {/each}
    </div>
  </section>
{/if}
