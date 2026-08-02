<script>
  import { t } from './i18n/index.js';
  import { onMount } from 'svelte';
  import { authParams, playlist, currentTrack, playerState } from './store.js';
  import TrackList from './TrackList.svelte';
  import { localDateString, memoryHeading, parseMemoryGroups } from './memories.js';

  const { onnavigate, initialYear = null } = $props();

  let groups = $state([]);
  let isLoading = $state(true);

  /**
   * Loads today's memories.
   *
   * The browser's own local date is sent along so that the groups match the device's today rather
   * than the server's, which matters as soon as the two are in different time zones.
   */
  async function loadMemories() {
    if (!$authParams) return;
    isLoading = true;
    try {
      const response = await fetch(`/rest/getMemories?date=${localDateString()}&${$authParams}`);
      if (response.ok) {
        const data = await response.json();
        groups = parseMemoryGroups(data);
      }
    } catch (e) {
      // An older or non-LMS server simply has no memories; that is not an error worth showing.
      console.error('Failed to load memories:', e);
      groups = [];
    } finally {
      isLoading = false;
    }
  }

  onMount(loadMemories);

  /** Plays one year group, in the order shown. */
  function playGroup(group) {
    if (group.songs.length === 0) return;
    playlist.set(group.songs);
    currentTrack.set(group.songs[0]);
    playerState.update((s) => ({ ...s, playing: true }));
  }

  $effect(() => {
    if (initialYear && groups.length > 0) {
      document.getElementById(`memories-year-${initialYear}`)?.scrollIntoView({ behavior: 'smooth' });
    }
  });
</script>

<div class="flex flex-col gap-8 pb-12">
  <header class="mb-2">
    <h1 class="text-4xl md:text-6xl font-black mb-2">{$t('memories.title')}</h1>
  </header>

  {#if isLoading}
    <p class="text-[#b3b3b3]">{$t('common.loading')}</p>
  {:else if groups.length === 0}
    <div class="flex flex-col gap-2">
      <p class="text-white font-bold">{$t('memories.empty')}</p>
      <p class="text-[#b3b3b3]">{$t('memories.emptyHelp')}</p>
    </div>
  {:else}
    {#each groups as group (group.year)}
      <section class="flex flex-col gap-4" id={`memories-year-${group.year}`}>
        <div class="flex items-center gap-4">
          <h2 class="text-2xl font-bold m-0">
            {$t(memoryHeading(group).key, memoryHeading(group).vars)}
          </h2>
          <button
            class="bg-brand text-black w-10 h-10 rounded-full flex items-center justify-center shadow-xl hover:scale-105 active:scale-95 transition cursor-pointer border-none"
            onclick={() => playGroup(group)}
            title={$t('common.playAll')}
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
              <path d="M7 6v12l10-6z"></path>
            </svg>
          </button>
          <span class="text-[#b3b3b3] text-sm">
            {group.year} • {$t('common.trackCount', { count: group.songs.length })}
          </span>
        </div>
        <TrackList tracks={group.songs} {onnavigate} />
      </section>
    {/each}
  {/if}
</div>
