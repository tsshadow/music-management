<script>
  import { missingArtistImages } from './coverArt.js';

  /**
   * The one artwork slot every player surface uses: a cover, or -- when the
   * track has none -- the artist's image, or -- when neither exists -- a flat
   * panel in the track's genre tint with its title. The three used to be three
   * separate `<img onerror>` chains scattered across `Player.svelte` and
   * `NowPlaying.svelte`, each falling back straight to `/images/spotify-fallback.svg`
   * regardless of whether an artist image was available; a library that is
   * mostly uncovered read as broken rather than merely undecorated.
   *
   * The fallback is explicit state rather than a chain of `onerror` handlers
   * that mutate `src` in place, because the old approach could not tell "this
   * track has no artist image" from "the browser hasn't tried yet" -- and it
   * never reset, so a real error on one track's cover kept skipping straight
   * to the panel for every track after it until a hard reload.
   */
  let {
    coverUrl = null,
    artistUrl = null,
    tint = null,
    title = '',
    alt = title,
    class: boxClass = '',
    rounded = 'rounded',
    large = false,
    panelTextClass = large ? 'text-2xl' : 'text-xs',
  } = $props();

  /**
   * Where a pair of URLs starts: cover first, then the artist image, then the
   * panel. A "writable derived" -- the error handlers below reassign it to
   * skip ahead, but because it is still a `$derived` it recomputes from
   * scratch the moment `coverUrl` or `artistUrl` changes, discarding any
   * override. That is what makes a stale error from the previous track unable
   * to skip the new one's cover: there is nothing to reset by hand.
   *
   * @type {'cover'|'artist'|'panel'}
   */
  let stage = $derived(coverUrl ? 'cover' : artistUrl ? 'artist' : 'panel');

  /** The cover failed to load (missing id, 404, offline placeholder never resolved) -- try the artist image next, or the panel if there is none. */
  function handleCoverError() {
    stage = artistUrl ? 'artist' : 'panel';
  }

  /**
   * The artist image failed too (MuMa has none for this artist) -- the panel is the only thing
   * left. Remembered, so the next row of the same artist starts at the panel rather than asking
   * the server the same question again (see `missingArtistImages`).
   */
  function handleArtistError() {
    if (artistUrl) missingArtistImages.add(artistUrl);
    stage = 'panel';
  }
</script>

{#if stage === 'cover'}
  <img
    src={coverUrl}
    {alt}
    class="{boxClass} {rounded} object-cover"
    onerror={handleCoverError}
  />
{:else if stage === 'artist'}
  <img
    src={artistUrl}
    {alt}
    class="{boxClass} {rounded} object-cover"
    onerror={handleArtistError}
  />
{:else}
  <!-- The tinted panel: no cover, no artist image, so the title is the only
       thing left to show. `bg-black/25` is `QuickAccessTile.svelte`'s
       readability wash -- a bright tint (Hardstyle orange) needs it exactly
       as much as a photo does. -->
  <div
    class="{boxClass} {rounded} relative overflow-hidden flex items-center justify-center"
    style="background-color: {tint || '#282828'}"
    data-testid="artwork-panel"
  >
    <span class="absolute inset-0 bg-black/25" aria-hidden="true"></span>
    <span class="relative z-10 {panelTextClass} font-bold text-white text-center line-clamp-3 px-2">{title}</span>
  </div>
{/if}
