<script>
  import { t } from './i18n/index.js';
  import { recentPlaces, placeTitle } from './recentPlaces.js';
  import { TILE_COLORS } from './browseColors.js';
  import QuickAccessTile from './QuickAccessTile.svelte';

  /**
   * Browse's "Recent" shelf: the last places this account opened on this
   * device (an artist, a genre, a playlist, ...), most recent first. Renders
   * nothing when there is nothing to show yet, and nothing for an id-based
   * place whose name has not resolved -- see `placeTitle` in
   * `recentPlaces.js`. Reuses `QuickAccessTile`, the same tile Home's own
   * shelves use, and `BrowseGrid`'s colour table so a place matches the
   * colour of its own category tile below it.
   */
  const { onnavigate } = $props();

  /** The kind's label, reusing whichever nav.* section name already exists; a preset has none of
   * its own, so it borrows the playlists label -- both are "a saved list of tracks" to a listener. */
  const KIND_LABEL_KEYS = {
    artist: 'nav.artists',
    album: 'nav.albums',
    genre: 'nav.genres',
    label: 'nav.labels',
    festival: 'nav.festivals',
    playlist: 'nav.playlists',
    preset: 'nav.playlists',
    year: 'nav.years',
    memories: 'nav.memories',
  };

  /** The kind's tile colour, borrowed from `BrowseGrid`'s table; a preset has no tile of its own
   * there either, so it takes the starred colour, same as `PresetGrid.svelte` does elsewhere. */
  const KIND_COLOR_KEYS = {
    artist: 'artists',
    album: 'albums',
    genre: 'genres',
    label: 'labels',
    festival: 'festivals',
    playlist: 'playlists',
    preset: 'starred',
    year: 'years',
    memories: 'memories',
  };

  const titled = $derived(
    $recentPlaces
      .map((place) => ({ place, title: placeTitle(place) }))
      .filter((entry) => entry.title),
  );
</script>

{#if titled.length > 0}
  <section class="flex flex-col gap-2">
    <h2 class="text-base font-bold m-0">{$t('mobile.recent')}</h2>
    <div class="flex gap-2 overflow-x-auto snap-x scrollbar-hide -mx-4 px-4 pb-1">
      {#each titled as { place, title } (place.view)}
        <QuickAccessTile
          class="w-[150px] shrink-0"
          {title}
          subtitle={$t(KIND_LABEL_KEYS[place.kind] ?? 'nav.playlists')}
          color={TILE_COLORS[KIND_COLOR_KEYS[place.kind] ?? 'playlists']}
          onclick={() => onnavigate?.(place.view)}
        />
      {/each}
    </div>
  </section>
{/if}
