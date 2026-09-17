<script>
  import { authParams, offline } from './store.js';
  import { coverArtSrc, FALLBACK, localCoverArt } from './coverArt.js';
  import { playTrack } from './playTrack.js';
  import Artwork from './Artwork.svelte';
  import ArtistList from './ArtistList.svelte';

  /**
   * One compact row for a Home shelf in `layout="rows"` mode: a 48px thumbnail, the title and
   * the artist, playing the track on tap. `HomeShelf.svelte` renders a vertical list of these
   * instead of `TrackCard`'s square cards for the "recently released"/"recently added" shelves
   * -- a shelf of large cards with mostly-placeholder artwork read as a row of blanks, while a
   * compact list reads as a real list even without covers.
   *
   * A `div[role="button"]`, not a native `<button>`, for the same reason `TrackCard.svelte`
   * uses one: `ArtistList` puts its own tappable spans inside the row, and a native `<button>`
   * may not contain another focusable control.
   */
  const { track, onnavigate } = $props();

  // Same fallback mapping `TrackCard.svelte` and the player use: `coverArtSrc` answers a
  // missing/unresolved cover with `FALLBACK` (the MuMa mark svg), but `Artwork` wants `null` so
  // it renders its own tinted title panel instead of that mark shrunk to thumbnail size.
  const coverUrl = $derived.by(() => {
    const src = coverArtSrc(track.coverArt, 100, $authParams, $localCoverArt, $offline);
    return src === FALLBACK ? null : src;
  });
</script>

<div
  role="button"
  tabindex="0"
  class="flex items-center gap-3 rounded-lg p-1 cursor-pointer hover:bg-[#282828] transition-colors"
  data-testid="track-row-compact"
  onclick={() => playTrack(track)}
  onkeydown={(e) => e.key === 'Enter' && playTrack(track)}
>
  <Artwork class="w-12 h-12 shrink-0" {coverUrl} artistUrl={null} title={track.title || track.name} alt={track.title} />
  <div class="flex-1 min-w-0">
    <div class="text-sm font-bold truncate">{track.title || track.name}</div>
    <div class="truncate">
      <ArtistList artist={track.artist} artistId={track.artistId} artists={track.artists} {onnavigate} />
    </div>
  </div>
</div>
