<script>
  /**
   * The full-screen player's stand-in while `NowPlaying.svelte`'s chunk is on its way (issue
   * #119). `NowPlaying` left the entry chunk, but opening it must still feel instant, so this
   * small component -- in the entry, next to the mini player -- draws the same screen from what
   * the player already knows: the tinted background, the header with "Playing from", the cover,
   * the title and the artist, and a working play/pause button. The rating, the progress bar and
   * the other transport buttons are skeleton blocks of the same size, so nothing moves when the
   * real view replaces this one. In practice the chunk is preloaded on idle and on a press of the
   * mini player, and this is on screen for a frame or two at most.
   *
   * It flies in like `NowPlaying` does; the real view then mounts already open, without a second
   * animation. A chunk that failed to load shows the section error with "Opnieuw" under the
   * header, which still closes the screen.
   *
   * @property {object|null} track - The playing track, as the mini player shows it.
   * @property {boolean} [playing]
   * @property {boolean} [transportLocked]
   * @property {string|null} [coverUrl]
   * @property {string|null} [artistUrl]
   * @property {string|null} [tint]
   * @property {boolean} [failed] - The chunk could not be loaded.
   * @property {() => void} [onretry]
   * @property {() => void} onclose
   * @property {() => void} [ontogglePlay]
   */
  import { t } from './i18n/index.js';
  import { fly } from 'svelte/transition';
  import { queueSource } from './store.js';
  import Artwork from './Artwork.svelte';
  import ArtistList from './ArtistList.svelte';
  import Skeleton from './loading/Skeleton.svelte';
  import SectionState from './loading/SectionState.svelte';
  import { nowPlayingBackground, playingFromLabel } from './nowPlayingContext.js';

  const {
    track = null,
    playing = false,
    transportLocked = false,
    coverUrl = null,
    artistUrl = null,
    tint = null,
    failed = false,
    onretry,
    onclose,
    ontogglePlay,
  } = $props();

  const playingFrom = $derived(playingFromLabel($queueSource, track, $t('queue.title')));
</script>

<div
  class="fixed inset-0 z-40 flex flex-col text-white"
  data-testid="now-playing-shell"
  data-tint={tint}
  style={nowPlayingBackground(tint)}
  aria-busy={!failed}
  in:fly={{ y: 600, duration: 250 }}
>
  <header class="flex items-center justify-between px-2 pt-[max(1rem,calc(0.5rem+env(safe-area-inset-top,0px)))] pb-2 shrink-0">
    <button
      class="bg-transparent border-none p-2 cursor-pointer text-white"
      onclick={onclose}
      aria-label={$t('nowPlaying.close')}
    >
      <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" aria-hidden="true">
        <path d="M16.59 8.59L12 13.17 7.41 8.59 6 10l6 6 6-6z"></path>
      </svg>
    </button>
    <div class="flex-1 min-w-0 text-center px-2">
      <span class="block text-[11px] text-muma-spotify-text">{$t('nowPlaying.playingFromLabel')}</span>
      <span class="block text-sm font-bold text-white truncate">{playingFrom}</span>
    </div>
    <!-- The menu button's slot, so the context line stays centred exactly where it will be. -->
    <div class="w-8 h-8" aria-hidden="true"></div>
  </header>

  {#if failed}
    <div class="flex-1 min-h-0 px-6">
      <SectionState status="error" {onretry} />
    </div>
  {:else}
    <div class="flex-1 min-h-0 overflow-hidden">
      <!-- The same stage as `NowPlaying.svelte` (see the long note there): the artwork box
           takes what the text and controls leave, the cover is the largest square in it, and
           landscape splits into two columns. -->
      <div class="mx-auto flex min-h-full h-full w-full max-w-xl flex-col justify-center px-6 pb-[calc(1rem+env(safe-area-inset-bottom,0px))] landscape:grid landscape:max-w-5xl landscape:grid-cols-2 landscape:items-center landscape:gap-x-10">
        <div class="relative min-h-0 flex-1 portrait:max-h-[calc(min(100vw,36rem)-1.5rem)] landscape:h-full">
          <div class="absolute inset-0 flex items-center justify-center py-3 landscape:py-4" style="container-type: size">
            <div class="aspect-square" style="width: min(100cqw, 100cqh)">
              {#if track}
                <Artwork
                  class="h-full w-full shadow-2xl"
                  rounded="rounded-lg"
                  large
                  {coverUrl}
                  {artistUrl}
                  {tint}
                  title={track.title}
                  alt={track.title}
                />
              {:else}
                <div class="h-full w-full rounded-lg bg-white/5"></div>
              {/if}
            </div>
          </div>
        </div>

        <div class="flex min-w-0 flex-none flex-col">
          {#if track}
            <div class="min-w-0">
              <p class="block w-full truncate m-0 text-left text-xl font-bold text-white" data-testid="now-playing-shell-title">{track.title}</p>
              <ArtistList artist={track.artist} artistId={track.artistId} artists={track.artists} size="lg" />
              {#if track.album}
                <div class="flex min-w-0 items-baseline gap-3 text-sm text-muma-spotify-text">
                  <span class="min-w-0 truncate">{track.album}</span>
                </div>
              {/if}
            </div>
            <div class="mx-auto mt-1 flex h-11 w-full max-w-xs items-center">
              <Skeleton class="h-7 w-full" />
            </div>
          {/if}

          <div class="mt-2">
            <Skeleton class="h-1 w-full" />
            <div class="mt-1 h-[16.5px]"></div>
          </div>

          <div class="-mx-2 mt-1 flex items-center justify-between">
            <Skeleton class="m-2 h-6 w-6 rounded-full" />
            <Skeleton class="m-2 h-7 w-7 rounded-full" />
            <button
              class="w-16 h-16 bg-white rounded-full text-black flex items-center justify-center cursor-pointer border-none {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}"
              onclick={ontogglePlay}
              disabled={transportLocked}
              aria-label={playing ? $t('nowPlaying.pause') : $t('nowPlaying.play')}
            >
              {#if playing}
                <svg viewBox="0 0 24 24" width="28" height="28" fill="black" aria-hidden="true">
                  <path d="M5.7 3a.7.7 0 0 0-.7.7v16.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V3.7a.7.7 0 0 0-.7-.7H5.7zm10 0a.7.7 0 0 0-.7.7v16.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V3.7a.7.7 0 0 0-.7-.7h-2.6z"></path>
                </svg>
              {:else}
                <svg viewBox="0 0 24 24" width="28" height="28" fill="black" aria-hidden="true">
                  <path d="M7.05 3.606l13.49 7.788a.7.7 0 0 1 0 1.212L7.05 20.394A.7.7 0 0 1 6 19.788V4.212a.7.7 0 0 1 1.05-.606z"></path>
                </svg>
              {/if}
            </button>
            <Skeleton class="m-2 h-7 w-7 rounded-full" />
            <Skeleton class="m-2 h-6 w-6 rounded-full" />
          </div>
        </div>
      </div>
    </div>
  {/if}
</div>
