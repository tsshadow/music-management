<script>
  import { t } from './i18n/index.js';
  import Artwork from './Artwork.svelte';
  import Throbber from './loading/Throbber.svelte';
  import { progressPercent } from './playerProgress.js';

  /**
   * The compact player: cover, title, artist, transport and (optionally) the rating, in whatever
   * small box it is given. It is the PC's always-on-top miniplayer window today
   * (`miniplayerWindow.js`, issue #177) and is built to be the phone's split-screen and
   * picture-in-picture layout too (docs/designs/miniplayer/).
   *
   * Like `NowPlaying.svelte` it reads no player store: every value comes from `Player.svelte` as
   * a prop and every button calls back into `Player.svelte`'s own function, so the window runs the
   * same code as the player bar and there is still one audio element.
   *
   * The layout follows the component's own size, not the window's: below 200px high it is a strip
   * (cover left, text and buttons right), from 200px a stack (cover on top). It uses no Svelte
   * transition and no animation frame: in the PC window it runs on the main tab's JavaScript, and
   * a hidden tab gets no animation frames.
   *
   * `variant` says where it is: `window` (the PC window), or `split` (the phone app in half of a
   * split screen, issue #179). `split` makes the transport as large as possible for a glance from a
   * bike -- 64px skip buttons, an 80px play button -- and adds two pills under it: "Navigeren
   * naast MuMa" when `onnavigate` is given, and "Volledige app" when `onexpand` is given.
   * `pip` (the phone app as a floating window, issue #178) shows the cover, title and artist only:
   * Android passes no tap into a floating window, so its buttons are the system's own.
   */

  let {
    track = null,
    playing = false,
    buffering = false,
    progress = 0,
    duration = 0,
    rating = 0,
    coverUrl = null,
    artistUrl = null,
    tint = null,
    transportLocked = false,
    playLocked = false,
    isLiveStation = false,
    restoringQueue = false,
    showRating = true,
    variant = 'window',
    ontogglePlay,
    onnext,
    onprev,
    onrate,
    onnavigate = null,
    onexpand = null,
  } = $props();

  const large = $derived(variant === 'split');
  const pip = $derived(variant === 'pip');
  const skipClass = $derived(large ? 'w-16 h-16 flex items-center justify-center' : 'p-0');
  const skipIcon = $derived(large ? 32 : 16);
  const playIcon = $derived(large ? 36 : 18);

  const showSkip = $derived(track !== null && !isLiveStation);
  const showStars = $derived(showRating && track !== null && !isLiveStation);
</script>

<div class="compact-player h-full w-full bg-muma-spotify-panel text-white" data-testid="compact-player" data-variant={variant}>
<div class="compact-layout">
  <div class="compact-cover">
    {#if track}
      <Artwork
        class="h-full w-full"
        rounded="rounded"
        {coverUrl}
        {artistUrl}
        {tint}
        title={track.title}
        alt={track.title}
        fit={isLiveStation ? 'contain' : 'cover'}
      />
    {:else if restoringQueue}
      <div class="h-full w-full bg-muma-skeleton rounded flex items-center justify-center text-muma-spotify-text">
        <Throbber size={20} label={$t('player.restoringQueue')} />
      </div>
    {:else}
      <div class="h-full w-full bg-white/5 rounded"></div>
    {/if}
  </div>

  <div class="compact-body min-w-0">
    <div class="min-w-0">
      {#if track}
        <div class="text-[13px] font-bold truncate" data-testid="compact-title">{track.title}</div>
        <div class="text-[11px] text-muma-spotify-text truncate">{track.artist}</div>
      {:else if restoringQueue}
        <div class="text-[13px] text-muma-spotify-text font-medium truncate">{$t('player.restoringQueue')}</div>
      {:else}
        <div class="text-[13px] text-muma-spotify-text italic font-medium truncate">{$t('player.nothingPlaying')}</div>
      {/if}
    </div>

    {#if !pip}
    <div class="flex items-center {large ? 'justify-center gap-6' : 'gap-3'}" data-testid="compact-transport">
      {#if showSkip}
        <button
          class="bg-transparent border-none {skipClass} text-muma-spotify-text hover:text-white transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          onclick={onprev}
          disabled={transportLocked}
          aria-label={$t('player.previous')}
        >
          <svg viewBox="0 0 16 16" width={skipIcon} height={skipIcon} fill="currentColor" aria-hidden="true">
            <path d="M3.3 1a.7.7 0 0 1 .7.7v5.15l9.95-5.744a.7.7 0 0 1 1.05.606v12.575a.7.7 0 0 1-1.05.607L4 9.15v5.15a.7.7 0 0 1-.7.7H1.7a.7.7 0 0 1-.7-.7V1.7a.7.7 0 0 1 .7-.7h1.6z"></path>
          </svg>
        </button>
      {/if}
      <button
        class="{large ? 'w-20 h-20' : 'w-9 h-9'} rounded-full bg-white text-black border-none flex items-center justify-center cursor-pointer hover:scale-105 transition-transform disabled:opacity-50 disabled:cursor-not-allowed"
        onclick={ontogglePlay}
        disabled={playLocked || (!track && !restoringQueue)}
        aria-label={playing ? $t('player.pause') : $t('common.play')}
        data-testid="compact-play"
      >
        {#if buffering}
          <Throbber size={playIcon} label={$t('player.buffering')} />
        {:else if playing}
          <svg viewBox="0 0 24 24" width={playIcon} height={playIcon} fill="currentColor" aria-hidden="true">
            <path d="M5.7 3a.7.7 0 0 0-.7.7v16.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V3.7a.7.7 0 0 0-.7-.7H5.7zm10 0a.7.7 0 0 0-.7.7v16.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V3.7a.7.7 0 0 0-.7-.7h-2.6z"></path>
          </svg>
        {:else}
          <svg viewBox="0 0 24 24" width={playIcon} height={playIcon} fill="currentColor" aria-hidden="true">
            <path d="M7.05 3.606l13.49 7.788a.7.7 0 0 1 0 1.212L7.05 20.394A.7.7 0 0 1 6 19.788V4.212a.7.7 0 0 1 1.05-.606z"></path>
          </svg>
        {/if}
      </button>
      {#if showSkip}
        <button
          class="bg-transparent border-none {skipClass} text-muma-spotify-text hover:text-white transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          onclick={onnext}
          disabled={transportLocked}
          aria-label={$t('player.next')}
        >
          <svg viewBox="0 0 24 24" width={skipIcon + 4} height={skipIcon + 4} fill="currentColor" aria-hidden="true">
            <path d="M16.7 3.3a.7.7 0 0 0-.7.7v6.85L6.05 4.806A.7.7 0 0 0 5 5.412v13.175a.7.7 0 0 0 1.05.607L16 13.15v6.85a.7.7 0 0 0 .7.7h1.6a.7.7 0 0 0 .7-.7V4a.7.7 0 0 0-.7-.7h-1.6z"></path>
          </svg>
        </button>
      {/if}
      {#if showStars}
        <div class="flex gap-0.5 ml-auto" data-testid="compact-stars">
          {#each [1, 2, 3, 4, 5] as star (star)}
            <button
              aria-label="{star} sterren"
              class="bg-transparent border-none p-0 cursor-pointer transition-colors {rating >= star ? 'text-brand' : 'text-white/10 hover:text-white/30'}"
              onclick={() => onrate?.(star)}
            >
              <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor" aria-hidden="true">
                <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"></path>
              </svg>
            </button>
          {/each}
        </div>
      {/if}
    </div>

    {#if onnavigate || onexpand}
      <div class="flex flex-wrap items-center justify-center gap-2">
        {#if onnavigate}
          <button
            class="bg-muma-spotify-light text-white border-none rounded-full px-4 min-h-11 text-sm font-bold cursor-pointer hover:bg-muma-spotify-hover"
            onclick={onnavigate}
            data-testid="compact-navigate"
          >
            {$t('miniplayer.navigate')}
          </button>
        {/if}
        {#if onexpand}
          <button
            class="bg-muma-spotify-light text-white border-none rounded-full px-4 min-h-11 text-sm font-bold cursor-pointer hover:bg-muma-spotify-hover"
            onclick={onexpand}
            data-testid="compact-expand"
          >
            {$t('miniplayer.fullApp')}
          </button>
        {/if}
      </div>
    {/if}
    {/if}
  </div>

  </div>

  {#if track && !isLiveStation && !pip}
    <div class="compact-progress bg-white/10" data-testid="compact-progress">
      <div class="h-full bg-white" style="width: {progressPercent(progress, duration)}%"></div>
    </div>
  {/if}
</div>

<style>
  /* Strip below 200px high, stack from 200px. The component's own size decides, so the same
     markup serves a small window and a large one (docs/designs/miniplayer/, decision 2). A
     container query cannot style the container itself, hence the inner layout element. */
  .compact-player {
    container: compact-player / size;
    position: relative;
    overflow: hidden;
  }

  .compact-layout {
    box-sizing: border-box;
    height: 100%;
    display: flex;
    flex-direction: row;
    align-items: center;
    gap: 12px;
    padding: 12px;
  }

  .compact-cover {
    flex: none;
    height: 100%;
    aspect-ratio: 1 / 1;
  }

  .compact-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 8px;
  }

  .compact-progress {
    position: absolute;
    left: 0;
    right: 0;
    bottom: 0;
    height: 2px;
  }

  @container compact-player (min-height: 200px) {
    .compact-layout {
      flex-direction: column;
      align-items: stretch;
    }

    .compact-cover {
      flex: 1;
      min-height: 0;
      height: auto;
      align-self: center;
    }

    .compact-body {
      flex: none;
    }
  }
</style>
