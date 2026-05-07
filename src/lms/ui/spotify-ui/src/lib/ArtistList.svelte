<script>
  import { createEventDispatcher } from 'svelte';
  const dispatch = createEventDispatcher();

  export let artist = '';
  export let artistId = '';
  export let artists = [];
  export let active = false;

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

<span class="text-sm {active ? 'text-spotify-green' : 'text-[#b3b3b3]'}">
  {#each displayArtists as a, i (a.id || i)}
    <span 
      role="link"
      tabindex={a.id ? 0 : -1}
      class="text-inherit hover:text-white {a.id ? 'hover:underline cursor-pointer' : ''}" 
      on:click|stopPropagation={() => { if (a.id) dispatch('navigate', `artist:${a.id}`); }}
      on:keydown|stopPropagation={(e) => { if (a.id && (e.key === 'Enter' || e.key === ' ')) dispatch('navigate', `artist:${a.id}`); }}
    >{a.name}</span>{#if i < displayArtists.length - 1}, {/if}
  {/each}
</span>

<style>
</style>
