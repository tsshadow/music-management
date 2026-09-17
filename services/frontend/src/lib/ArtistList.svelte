<script>
  /**
   * One or more artist names as a comma-joined list, each name its own tap
   * target when it has an id -- the same small component every screen that
   * shows a track's artist uses, so the tap-target and hover behaviour is
   * defined once.
   *
   * `size="lg"` is the full player header's variant (increment B): a taller
   * row with a trailing chevron so the whole line reads as "go to artist"
   * even though, with several artists, only each name individually is.
   */
  const { artist = '', artistId = '', artists = [], active = false, size = 'sm', onnavigate } = $props();

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

  /** The chevron only makes sense once there is somewhere for the row to lead. */
  const hasNavigable = $derived(displayArtists.some((a) => a.id));
</script>

<span
  class="{size === 'lg' ? 'flex items-center py-2 min-h-11 text-base' : 'text-sm'} {active ? 'text-brand' : 'text-[#b3b3b3]'}"
>
  {#each displayArtists as a, i (a.id || i)}
    <span
      role="link"
      tabindex={a.id ? 0 : -1}
      class="text-inherit hover:text-white {a.id ? 'hover:underline cursor-pointer' : ''}"
      onclick={(e) => { e.stopPropagation(); if (a.id && onnavigate) onnavigate(`artist:${a.id}`); }}
      onkeydown={(e) => { e.stopPropagation(); if (a.id && onnavigate && (e.key === 'Enter' || e.key === ' ')) onnavigate(`artist:${a.id}`); }}
    >{a.name}</span>{#if i < displayArtists.length - 1}, {/if}
  {/each}
  {#if size === 'lg' && hasNavigable}
    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" class="text-[#b3b3b3] shrink-0 ml-1" aria-hidden="true">
      <path d="M8.59 16.59L13.17 12 8.59 7.41 10 6l6 6-6 6z"></path>
    </svg>
  {/if}
</span>

<style>
</style>
