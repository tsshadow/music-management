<script>
  /**
   * The Radio page: the live stations and the MuMa Radio channels, in one list that scrolls like
   * the genres. A tap on a row starts it, and a tap on the row that plays stops it.
   * See docs/designs/live-radio-stations/functional.md.
   */
  import { onMount } from 'svelte';
  import { t } from './i18n/index.js';
  import { knownStations, liveStation, mumaApiKey, mumaApiUrl, radioChannel } from './store.js';
  import { describeFilter } from './management/radioChannels.js';
  import { leaveRadio, tuneChannel, tuneStation } from './radioCommands.js';

  let channels = $state([]);
  let stations = $state([]);
  let loading = $state(true);
  let failed = $state(false);

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

  {#if stations.length}
    <h2 class="text-xl font-bold mb-2">{$t('radio.stationsHeading')}</h2>
    <div class="flex flex-col mb-8">
      {#each stations as station (station.slug)}
        {@const active = $liveStation?.slug === station.slug}
        <button
          type="button"
          class="{rowClass} text-sm font-bold"
          style="color: {active ? '#b266ff' : 'white'}"
          aria-pressed={active}
          onclick={() => pickStation(station)}
        >
          {station.name}
        </button>
      {/each}
    </div>
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
