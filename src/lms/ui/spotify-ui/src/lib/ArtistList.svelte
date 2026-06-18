<script>
  const { artist = '', artistId = '', artists = [], active = false, onnavigate } = $props();

  const displayArtists = $derived.by(() => {
    if (artists && artists.length > 0) {
      return artists;
    }
    if (artist) {
      const names = artist.split(', ');
      return names.map((name, i) => ({
        name: name,
        id: i === 0 ? artistId : null
      }));
    }
    return [];
  });
</script>

<span class="text-sm {active ? 'text-brand' : 'text-[#b3b3b3]'}">
  {#each displayArtists as a, i (a.id || i)}
    <span 
      role="link"
      tabindex={a.id ? 0 : -1}
      class="text-inherit hover:text-white {a.id ? 'hover:underline cursor-pointer' : ''}" 
      onclick={(e) => { e.stopPropagation(); if (a.id && onnavigate) onnavigate(`artist:${a.id}`); }}
      onkeydown={(e) => { e.stopPropagation(); if (a.id && onnavigate && (e.key === 'Enter' || e.key === ' ')) onnavigate(`artist:${a.id}`); }}
    >{a.name}</span>{#if i < displayArtists.length - 1}, {/if}
  {/each}
</span>

<style>
</style>
