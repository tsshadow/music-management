<script>
  /**
   * The Radio page: the favorite and recent stations at the top, then every station as a logo, then
   * the MuMa Radio channels. A tap starts a station, and a tap on the one that plays stops it.
   * See docs/designs/live-radio-stations/functional.md.
   */
  import { onMount } from 'svelte';
  import { t } from './i18n/index.js';
  import { favoriteStations, knownStations, liveStation, mumaApiKey, mumaApiUrl, radioChannel, recentStations } from './store.js';
  import { stationLogoUrl, stationSections, withFavoriteToggled } from './liveStation.js';
  import { describeFilter } from './management/radioChannels.js';
  import { leaveRadio, tuneChannel, tuneStation } from './radioCommands.js';

  let channels = $state([]);
  let stations = $state([]);
  let loading = $state(true);
  let failed = $state(false);
  let query = $state('');
  // The slugs without a logo file: a station a curator added. These show their name.
  let withoutLogo = $state({});

  /** A search box is noise for a short list. */
  const SEARCH_FROM_STATIONS = 12;

  const sections = $derived(stationSections(stations, $favoriteStations, $recentStations, query));

  /**
   * Reads one list. A list that does not load stays empty, so the other list still works.
   *
   * @param {string} path - The API path.
   * @param {string} key - The key of the list in the answer.
   * @returns {Promise<Array<object>|null>} The list, or null when the request failed.
   */
  async function readList(path, key) {
    try {
      const response = await fetch(`${$mumaApiUrl}${path}`, { headers: { 'X-API-Key': $mumaApiKey } });
      if (!response.ok) return null;
      return (await response.json())[key] || [];
    } catch (e) {
      console.error($t('radio.couldNotLoad'), e);
      return null;
    }
  }

  onMount(async () => {
    const [channelList, stationList] = await Promise.all([
      readList('/api/radio/channels', 'channels'),
      readList('/api/radio/stations', 'stations'),
    ]);
    channels = channelList ?? [];
    stations = stationList ?? [];
    knownStations.set(stations);
    failed = channelList === null && stationList === null;
    loading = false;
  });

  /**
   * Starts a station, or stops it when it plays.
   *
   * @param {{slug: string}} station
   */
  function pickStation(station) {
    if ($liveStation?.slug === station.slug) leaveRadio();
    else tuneStation(station);
  }

  /**
   * Starts a channel, or stops it when it plays.
   *
   * @param {{slug: string}} channel
   */
  function pickChannel(channel) {
    if ($radioChannel === channel.slug) leaveRadio();
    else tuneChannel(channel);
  }

  const rowClass =
    'w-full text-left px-4 py-3 bg-transparent border-none rounded-md cursor-pointer hover:bg-white/10 transition-colors';
</script>

<div data-testid="radio-view">
  <h1 class="text-4xl md:text-6xl font-black mb-6">{$t('nav.radio')}</h1>

  {#if failed}
    <p class="text-sm text-muma-spotify-text">{$t('radio.couldNotLoad')}</p>
  {:else if !loading && !channels.length && !stations.length}
    <p class="text-sm text-muma-spotify-text">{$t('radio.noChannels')}</p>
  {/if}

  {#snippet tile(station)}
    {@const active = $liveStation?.slug === station.slug}
    {@const favorite = $favoriteStations.includes(station.slug)}
    <div class="relative min-w-0" data-testid="station-tile">
      <button
        type="button"
        class="block w-full bg-transparent border-none p-0 text-left cursor-pointer"
        aria-pressed={active}
        onclick={() => pickStation(station)}
      >
        <span class="block aspect-[8/5] overflow-hidden rounded-md bg-white/10 {active ? 'ring-2 ring-[#b266ff]' : ''}">
          {#if withoutLogo[station.slug]}
            <span class="flex h-full w-full items-center justify-center px-2 text-center text-sm font-bold text-white">{station.name}</span>
          {:else}
            <img
              src={stationLogoUrl(station.slug)}
              alt=""
              loading="lazy"
              class="block h-full w-full object-cover"
              onerror={() => (withoutLogo[station.slug] = true)}
            />
          {/if}
        </span>
        <span class="mt-1 block truncate text-[12px] font-bold" style="color: {active ? '#b266ff' : 'white'}">{station.name}</span>
      </button>
      <button
        type="button"
        class="absolute right-1 top-1 flex h-8 w-8 items-center justify-center rounded-full border-none bg-black/60 cursor-pointer {favorite ? 'text-brand' : 'text-white'}"
        aria-label={$t(favorite ? 'radio.removeFavorite' : 'radio.addFavorite', { name: station.name })}
        aria-pressed={favorite}
        onclick={() => favoriteStations.update((slugs) => withFavoriteToggled(slugs, station.slug))}
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill={favorite ? 'currentColor' : 'none'} stroke="currentColor" stroke-width={favorite ? 0 : 2} aria-hidden="true">
          <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"></path>
        </svg>
      </button>
    </div>
  {/snippet}

  {#snippet grid(heading, list, testid)}
    {#if list.length}
      <h2 class="text-xl font-bold mb-3">{heading}</h2>
      <div class="grid grid-cols-3 gap-3 mb-8 md:grid-cols-5 xl:grid-cols-7" data-testid={testid}>
        {#each list as station (station.slug)}
          {@render tile(station)}
        {/each}
      </div>
    {/if}
  {/snippet}

  {#if stations.length >= SEARCH_FROM_STATIONS}
    <input
      type="search"
      class="w-full mb-6 rounded-md border-none bg-white/10 px-4 py-3 text-sm text-white placeholder:text-muma-spotify-text"
      placeholder={$t('radio.searchStations')}
      aria-label={$t('radio.searchStations')}
      bind:value={query}
      data-testid="station-search"
    />
  {/if}

  {@render grid($t('radio.favoritesHeading'), sections.favorites, 'stations-favorites')}
  {@render grid($t('radio.recentHeading'), sections.recent, 'stations-recent')}
  {@render grid($t('radio.stationsHeading'), sections.all, 'stations-all')}
  {#if query.trim() && !sections.all.length}
    <p class="text-sm text-muma-spotify-text mb-8">{$t('radio.noStationMatch')}</p>
  {/if}

  {#if channels.length}
    <h2 class="text-xl font-bold mb-2">{$t('radio.channelsHeading')}</h2>
    <div class="flex flex-col">
      {#each channels as channel (channel.slug)}
        {@const active = $radioChannel === channel.slug}
        <button
          type="button"
          class={rowClass}
          style="color: {active ? '#b266ff' : 'white'}"
          aria-pressed={active}
          onclick={() => pickChannel(channel)}
        >
          <span class="block text-sm font-bold">{channel.name}</span>
          <span class="block text-[12px] text-muma-spotify-text">
            {describeFilter(channel.filter, $t('management.radio.wholeLibrary'))}
          </span>
        </button>
      {/each}
    </div>
  {/if}
</div>
