<script>
  import { onMount } from 'svelte';
  import { t } from './i18n/index.js';
  import { authParams, restUrl, viewMode, memoriesOnHomeEnabled, homeModeReleaseRadar, homeModeDailyMix,
    homeModeFavorites, homeModeRecentlyReleased, homeModeRecentlyAdded } from './store.js';
  import { memoryCount } from './memories.js';
  import { listOf, subsonicJson } from './subsonic.js';
  import QuickAccessTile from './QuickAccessTile.svelte';
  import HomeShelf from './HomeShelf.svelte';

  /** Phone home maps the account's section modes to tiles or shelves over existing sources. */
  const { sections = [], memoryGroups = [], onnavigate, onrecent = null } = $props();
  let favorites = $state([]);
  let recentlyReleased = $state([]);
  let recentlyAdded = $state([]);
  const destinations = $derived([
    { id: 'release-radar', key: 'nav.releaseRadar', mode: $homeModeReleaseRadar, tracks: source('feed:release-radar') },
    { id: 'daily-mix', key: 'nav.dailyMix', mode: $homeModeDailyMix, tracks: source('feed:daily-mix') },
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
      cover={cover(memoryGroups[0]?.songs[0])} onclick={() => onnavigate('memories')} />
  {/if}
  {#each destinations.filter(section => section.mode === 'BUTTON') as section (section.id)}
    <QuickAccessTile title={$t(section.key)} subtitle={subtitle(section)}
      cover={cover(section.tracks[0])} onclick={() => openSection(section)} />
  {/each}
</div>
{#each destinations.filter(section => section.mode === 'OVERVIEW') as section (section.id)}
  <HomeShelf title={$t(section.key)} tracks={section.tracks.slice(0, 6)}
    noTracksText={$t('dashboard.noTracksInSection')} showAllLabel={$t('dashboard.showAll')}
    {onnavigate} onshowall={() => openSection(section)} />
{/each}
