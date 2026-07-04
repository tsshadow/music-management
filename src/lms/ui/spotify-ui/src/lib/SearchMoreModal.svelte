<script>
  import { onMount } from 'svelte';
  import { authParams, viewMode, activeModal, activeView, deduplicateEnabled } from './store.js';
  import { deduplicateTracks } from './deduplicate.js';
  import TrackList from './TrackList.svelte';
  import ArtistList from './ArtistList.svelte';
  import Modal from './Modal.svelte';

  /**
   * @typedef {Object} Props
   * @property {string} query - The search query.
   * @property {'tracks' | 'artists' | 'albums'} category - The category to show more of.
   */

  /** @type {Props} */
  let { query, category } = $props();
  
  let items = $state([]);
  let loading = $state(true);

  async function performSearch() {
    loading = true;
    try {
      const durationFilter = $viewMode === 'sets' ? '&minDuration=10' : '&maxDuration=10';
      // Fetch more results for the specific category
      const artistCount = category === 'artists' ? 100 : 1;
      const albumCount = category === 'albums' ? 100 : 1;
      const songCount = category === 'tracks' ? 100 : 1;
      
      const response = await fetch(`/rest/search3?${$authParams}&query=${encodeURIComponent(query)}&artistCount=${artistCount}&albumCount=${albumCount}&songCount=${songCount}${durationFilter}`);
      const data = await response.json();
      const searchResult = data['subsonic-response']?.searchResult3 || {};
      
      if (category === 'tracks') items = $deduplicateEnabled ? deduplicateTracks(searchResult.song || []) : (searchResult.song || []);
      else if (category === 'artists') items = searchResult.artist || [];
      else if (category === 'albums') items = searchResult.album || [];
    } catch (e) {
      console.error("Search failed:", e);
    } finally {
      loading = false;
    }
  }

  onMount(performSearch);

  const titleText = $derived(
    (category === 'tracks' ? ($viewMode === 'sets' ? 'Sets' : 'Nummers') :
     category === 'artists' ? 'Artiesten' :
     category === 'albums' ? 'Albums' : 'Resultaten') + ` voor "${query}"`
  );

  function close() {
    activeModal.set(null);
  }

  function navigate(view) {
    activeView.set(view);
    close();
  }

  function getArtistImageUrl(artist, auth) {
    if (artist.coverArt) {
        return `/rest/getCoverArt?id=${artist.coverArt}&size=300&${auth}`;
    }
    return '/images/unknown-artist.svg';
  }
</script>

<Modal title={titleText} onclose={close}>
  {#if loading}
    <div class="flex justify-center py-12">
      <div class="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-white"></div>
    </div>
  {:else if items.length === 0}
    <div class="text-[#b3b3b3] p-12 text-center border border-white/5 rounded-xl bg-white/5">
        <p class="text-xl font-bold mb-2 text-white">Geen resultaten gevonden</p>
        <p class="text-sm opacity-60">Probeer een andere zoekterm.</p>
    </div>
  {:else}
    {#if category === 'tracks'}
      <TrackList tracks={items} onnavigate={navigate} />
    {:else if category === 'artists'}
      <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
        {#each items as artist (artist.id)}
          <div
            role="button"
            tabindex="0"
            class="bg-[#181818] p-4 rounded-lg flex flex-col gap-3 cursor-pointer transition-colors hover:bg-[#282828]"
            onclick={() => navigate(`artist:${artist.id}`)}
            onkeydown={(e) => e.key === 'Enter' && navigate(`artist:${artist.id}`)}
          >
              <img
                src={getArtistImageUrl(artist, $authParams)}
                alt={artist.name}
                class="w-full aspect-square object-cover rounded-full shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                onerror={(e) => e.target.src = '/images/unknown-artist.svg'}
              />
              <span class="font-bold whitespace-nowrap overflow-hidden text-ellipsis">{artist.name}</span>
              <span class="text-sm text-[#b3b3b3]">Artiest</span>
          </div>
        {/each}
      </div>
    {:else if category === 'albums'}
      <div class="grid grid-cols-[repeat(auto-fill,minmax(150px,1fr))] md:grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-4 md:gap-6">
        {#each items as album (album.id)}
          <div
            role="button"
            tabindex="0"
            class="bg-[#181818] p-4 rounded-lg flex flex-col gap-3 cursor-pointer transition-colors hover:bg-[#282828]"
            onclick={() => navigate(`album:${album.id}`)}
            onkeydown={(e) => e.key === 'Enter' && navigate(`album:${album.id}`)}
          >
              <img
                src={album.coverArt ? `/rest/getCoverArt?id=${album.coverArt}&size=300&${$authParams}` : '/images/spotify-fallback.svg'}
                alt={album.name}
                class="w-full aspect-square object-cover rounded shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
                onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
              />
              <span class="font-bold whitespace-nowrap overflow-hidden text-ellipsis">{album.name}</span>
              <ArtistList
                artist={album.artist}
                artistId={album.artistId}
                artists={album.albumArtists}
                onnavigate={navigate}
              />
          </div>
        {/each}
      </div>
    {/if}
  {/if}
</Modal>
