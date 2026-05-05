<script>
  import { createEventDispatcher } from 'svelte';
  const dispatch = createEventDispatcher();

  export let artist = '';
  export let artistId = '';
  export let artists = [];

  let displayArtists = [];

  $: {
    if (artists && artists.length > 0) {
      displayArtists = artists;
    } else if (artist) {
      const names = artist.split(', ');
      displayArtists = names.map((name, i) => ({
        name: name,
        id: i === 0 ? artistId : null
      }));
    } else {
      displayArtists = [];
    }
  }
</script>

<span class="artist-list">
  {#each displayArtists as a, i}
    <span class="artist-item {a.id ? 'hover:underline cursor-pointer' : ''}" on:click|stopPropagation={() => { if (a.id) dispatch('navigate', `artist:${a.id}`); }}>{a.name}</span>{#if i < displayArtists.length - 1}, {/if}
  {/each}
</span>

<style>
  .artist-list {
    color: #b3b3b3;
    font-size: 14px;
  }
  .artist-item {
    color: inherit;
  }
  .artist-item:hover {
    color: #fff;
  }
</style>
