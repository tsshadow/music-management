<script>
  import { onMount } from 'svelte';
  import { t } from './i18n/index.js';
  import { authParams, restUrl, viewMode, memoriesOnHomeEnabled, homeModeReleaseRadar, homeModeDailyMix,
    homeModeFavorites, homeModeRecentlyReleased, homeModeRecentlyAdded } from './store.js';
  import { memoryCount } from './memories.js';
  import { listOf, subsonicJson } from './subsonic.js';
  import QuickAccessTile from './QuickAccessTile.svelte';
  import HomeShelf from './HomeShelf.svelte';
  import DailyMixesShelf from './DailyMixesShelf.svelte';

  /** Phone home maps the account's section modes to tiles or shelves over existing sources. */
  const { sections = [], memoryGroups = [], onnavigate, onrecent = null } = $props();

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
  let favorites = $state([]);
  let recentlyReleased = $state([]);
  let recentlyAdded = $state([]);
  const destinations = $derived([
    { id: 'release-radar', key: 'nav.releaseRadar', mode: $homeModeReleaseRadar, tracks: source('feed:release-radar') },
    // The five daily mixes are not a track list -- each is its own colour and its own page -- so
    // this entry only carries the mode; DailyMixesShelf/QuickAccessTile below render it specially.
    { id: 'daily-mixes', kind: 'mixes', key: 'nav.dailyMixes', mode: $homeModeDailyMix },
    { id: 'starred', key: 'nav.starred', mode: $homeModeFavorites, tracks: favorites },
    { id: 'recently-released', sort: 'recent', view: $viewMode, key: 'settings.general.home.recentlyReleased', mode: $homeModeRecentlyReleased, tracks: recentlyReleased },
    { id: 'recently-added', sort: 'added', view: $viewMode, key: 'settings.general.home.recentlyAdded', mode: $homeModeRecentlyAdded, tracks: recentlyAdded },
  ]);
  // SHORTCUTS has no recent-places store in the web UI. Its saved mode intentionally renders nothing.

  /** Opening a recent shelf keeps its ordering in the full track list. */
  function openSection(section) {
    if (section.sort && onrecent) onrecent(section.sort);
    else onnavigate(section.view ?? section.id);
  }

  /** Read an already-loaded home source without starting another request. */
  function source(id) { return sections.find(section => section.id === id)?.tracks ?? []; }

  /**
   * The line under a tile's title. A feed's home copy is capped (`HOME_FEED_ROWS` in
   * Dashboard) and the recent lists ask for six, so a count there would read "10 nummers"
   * on every tile whatever the feed holds; the first track says something true instead.
   * Favourites is the one list fetched whole, so its count is real.
   *
   * @param {object} section
   * @returns {string}
   */
  function subtitle(section) {
    if (section.id === 'starred') return $t('common.trackCount', { count: section.tracks.length });
    const first = section.tracks[0];
    if (!first) return $t('dashboard.noTracksInSection');
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
    if (!$authParams) return;
    let stale = false;
    Promise.all(['recent', 'added'].map(sort => subsonicJson('getSpotifyTracks', {
      sort, count: 6, offset: 0, ...duration,
    }).then(data => listOf(data, 'tracks.track')).catch(error => {
      console.warn('Could not load recent home tracks', error);
      return [];
    }))).then(([released, added]) => {
      if (stale) return;
      recentlyReleased = released;
      recentlyAdded = added;
    });
    return () => { stale = true; };
  });

  onMount(async () => {
    if (!$authParams) return;
    try { favorites = listOf(await subsonicJson('getStarred2'), 'starred2.song'); }
    catch (error) { console.warn('Could not load home favourites', error); }
  });
</script>

<div class="grid grid-cols-2 gap-2" data-testid="home-quick-access">
  {#if $memoriesOnHomeEnabled}
    <QuickAccessTile title={$t('memories.title')}
      subtitle={$t('memories.homeSummary', { years: memoryGroups.length, tracks: memoryGroups.reduce((count, group) => count + memoryCount(group), 0) })}
      cover={cover(memoryGroups[0]?.songs[0])} color={TILE_COLORS.memories} icon={TILE_ICONS.memories}
      onclick={() => onnavigate('memories')} />
  {/if}
  {#each destinations.filter(section => section.mode === 'BUTTON') as section (section.id)}
    {#if section.kind === 'mixes'}
      <QuickAccessTile title={$t(section.key)} subtitle={$t('dashboard.dailyMixesSubtitle')}
        color={TILE_COLORS[section.id]} icon={TILE_ICONS[section.id]}
        onclick={() => onnavigate('daily-mixes')} />
    {:else}
      <QuickAccessTile title={$t(section.key)} subtitle={subtitle(section)}
        cover={cover(section.tracks[0])} color={TILE_COLORS[section.id]} icon={TILE_ICONS[section.id]}
        onclick={() => openSection(section)} />
    {/if}
  {/each}
</div>
{#each destinations.filter(section => section.mode === 'OVERVIEW') as section (section.id)}
  {#if section.kind === 'mixes'}
    <DailyMixesShelf {onnavigate} />
  {:else}
    <HomeShelf title={$t(section.key)} tracks={section.tracks.slice(0, 6)}
      noTracksText={$t('dashboard.noTracksInSection')} showAllLabel={$t('dashboard.showAll')}
      {onnavigate} onshowall={() => openSection(section)} />
  {/if}
{/each}
