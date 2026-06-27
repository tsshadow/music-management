<script>
  import { authParams } from './store.js';
  import TrackList from './TrackList.svelte';

  const { onnavigate } = $props();

  let history = $state([]);
  let isLoading = $state(false);
  let offset = $state(0);
  const pageSize = 50;
  let hasMore = $state(true);

  /**
   * Loads the listen history from the backend.
   *
   * @param {boolean} [append=false] - Whether to append results to the existing list.
   */
  async function loadHistory(append = false) {
    if (!$authParams) return;
    if (!append) {
        offset = 0;
        hasMore = true;
    }
    if (!hasMore) return;

    isLoading = true;
    try {
        const response = await fetch(`/rest/getSpotifyHistory?offset=${offset}&count=${pageSize}&${$authParams}`);
        if (!response.ok) throw new Error('Network response was not ok');
        const data = await response.json();
        const entries = data['subsonic-response']?.history?.entry || [];
        const entriesArr = Array.isArray(entries) ? entries : [entries];
        
        const mappedEntries = entriesArr.map(entry => ({
            ...entry,
            listenedAt: entry.listenedAt
        }));

        if (append) {
            history = [...history, ...mappedEntries];
        } else {
            history = mappedEntries;
        }

        const moreResults = data['subsonic-response']?.history?.moreResults;
        hasMore = moreResults !== undefined ? (String(moreResults) === 'true' || moreResults === true) : mappedEntries.length === pageSize;
        offset += mappedEntries.length;
    } catch (e) {
        console.error("Failed to load history:", e);
    } finally {
        isLoading = false;
    }
  }

  $effect(() => {
    if ($authParams) {
        loadHistory();
    }
  });
</script>

<div class="p-8">
  <div class="flex items-center justify-between mb-8">
    <div>
      <h2 class="text-3xl font-bold mb-2">Luistergeschiedenis</h2>
      <p class="text-[#b3b3b3]">Jouw recent beluisterde nummers.</p>
    </div>
    <button 
        class="bg-[#282828] text-white px-4 py-2 rounded-full font-bold hover:scale-105 transition-transform"
        onclick={() => loadHistory(false)}
    >
        Vernieuwen
    </button>
  </div>

  {#if history.length > 0}
    <TrackList tracks={history} showDate={true} onnavigate={onnavigate} />
    
    {#if hasMore}
        <div class="flex justify-center mt-8">
            <button 
                class="bg-white text-black px-8 py-3 rounded-full font-bold hover:scale-105 transition-transform disabled:opacity-50"
                onclick={() => loadHistory(true)}
                disabled={isLoading}
            >
                {isLoading ? 'Laden...' : 'Meer laden'}
            </button>
        </div>
    {/if}
  {:else if isLoading}
    <div class="flex justify-center py-20">
      <div class="animate-spin rounded-full h-12 w-12 border-b-2 border-brand"></div>
    </div>
  {:else}
    <div class="text-center py-20">
      <p class="text-[#b3b3b3] text-lg">Nog geen luistergeschiedenis gevonden.</p>
    </div>
  {/if}
</div>
