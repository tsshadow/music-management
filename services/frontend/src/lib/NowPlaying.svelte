<script>
  import { t } from './i18n/index.js';
  import { fly } from 'svelte/transition';
  import { formatTime, formatClock, progressPercent } from './playerProgress.js';
  import BottomSheet from './BottomSheet.svelte';

  /**
   * The phone's full-screen "Now Playing" view, opened by a tap on the mini
   * player (see `Player.svelte`'s `handleMiniPlayerTap`). Everything it shows
   * -- the track, the transport, the rating -- is state `Player.svelte` already
   * computed for the mini player; this component takes it as props rather than
   * reading the stores a second time, and every action (play/pause, seek,
   * rate, shuffle, repeat, the equalizer and the queue) calls straight back
   * into the same functions the mini player uses, so there is exactly one
   * place that decides what any of them do.
   *
   * Closing goes through the caller's `onclose` in every case -- the chevron,
   * a swipe down on the cover, and the shell/browser back button (see
   * `closeNowPlaying` in `store.js` and the back-handling in `App.svelte`) --
   * so there is one answer for "did this consume the back press" rather than
   * three.
   */

  let {
    open = false,
    track = null,
    playing = false,
    progress = 0,
    duration = 0,
    rating = 0,
    shuffleMode = false,
    repeatMode = 'none',
    transportLocked = false,
    coverUrl = '/images/spotify-fallback.svg',
    equalizerSupported = false,
    isSetMode = false,
    lyricsLines = [],
    onclose,
    ontogglePlay,
    onnext,
    onprev,
    onrate,
    ontoggleShuffle,
    ontoggleRepeat,
    onseek,
    onseekTo,
    onskip,
    ontoggleEqualizer,
    ontoggleQueue,
  } = $props();

  // What the context line reads. A track almost always carries its album; the
  // rare case without one (radio, a bulletin) reads as the queue instead of an
  // empty line.
  const playingFrom = $derived(track?.album || $t('queue.title'));

  let touchStartY = $state(null);
  let showLyricsSheet = $state(false);

  function handleTouchStart(e) {
    touchStartY = e.touches?.[0]?.clientY ?? null;
  }

  /**
   * A firm downward drag on the cover closes the view, the same gesture
   * Spotify uses. 80px is well past an accidental brush or the start of a
   * vertical scroll -- there is nothing to scroll here, but the threshold
   * still keeps a short, undecided touch from closing the screen.
   *
   * @param {TouchEvent} e
   */
  function handleTouchEnd(e) {
    if (touchStartY === null) return;
    const endY = e.changedTouches?.[0]?.clientY ?? touchStartY;
    const delta = endY - touchStartY;
    touchStartY = null;
    if (delta > 80) onclose?.();
  }
</script>

{#if open}
  <!--
    `in:fly` only, not `transition:fly`: jsdom's `element.animate()` shim
    renders an intro but never resolves an outro (see the same note on
    `BottomSheet.svelte`), which would leave this stuck in the DOM after every
    close in a test -- closing for real users, just not observably so there.
  -->
  <div
    class="fixed inset-0 z-40 bg-[#121212] flex flex-col text-white"
    data-testid="now-playing"
    in:fly={{ y: 600, duration: 250 }}
  >
    <header class="flex items-center justify-between px-2 pt-[max(1rem,env(safe-area-inset-top))] pb-2 shrink-0">
      <button
        class="bg-transparent border-none p-2 cursor-pointer text-white"
        onclick={onclose}
        aria-label={$t('nowPlaying.close')}
      >
        <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" aria-hidden="true">
          <path d="M16.59 8.59L12 13.17 7.41 8.59 6 10l6 6 6-6z"></path>
        </svg>
      </button>
      <div class="flex-1 text-center text-[11px] font-bold uppercase tracking-wide text-[#b3b3b3] truncate px-2">
        {$t('nowPlaying.playingFrom', { name: playingFrom })}
      </div>
      {#if lyricsLines.length > 0}
        <button
          class="w-8 h-8 flex items-center justify-center text-white bg-transparent border-none cursor-pointer"
          onclick={() => (showLyricsSheet = true)}
          aria-label={$t('track.lyrics')}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
            <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"></path>
          </svg>
        </button>
      {:else}
        <!-- No lyrics for this track: the spacer keeps the title centered
             rather than shifting it once one shows up on the next track. -->
        <div class="w-8 h-8" aria-hidden="true"></div>
      {/if}
    </header>

    <div class="flex-1 flex flex-col px-6 pb-6 min-h-0 overflow-y-auto">
      <!-- `role="presentation"`: the swipe-to-close gesture is a bonus on top
           of the chevron button above, which is the one thing assistive tech
           and keyboard users need -- this element carries no interactive
           semantics of its own. -->
      <div
        class="w-full aspect-square mb-6"
        role="presentation"
        ontouchstart={handleTouchStart}
        ontouchend={handleTouchEnd}
      >
        {#if track}
          <img
            src={coverUrl}
            alt={track.title}
            class="w-full h-full rounded-lg shadow-2xl object-cover"
            onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
          />
        {:else}
          <div class="w-full h-full rounded-lg bg-white/5 flex items-center justify-center">
            <img src="/images/spotify-fallback.svg" alt="" class="w-1/2 h-1/2 opacity-30" />
          </div>
        {/if}
      </div>

      {#if track}
        <div class="min-w-0 mb-4">
          <div class="text-xl font-bold truncate">{track.title}</div>
          <div class="text-sm text-[#b3b3b3] truncate">{track.artist}</div>
        </div>

        <div class="flex items-center gap-1 mb-6">
          {#each [1, 2, 3, 4, 5] as star (star)}
            <button
              aria-label="{star} sterren"
              class="bg-transparent border-none p-0.5 cursor-pointer transition-colors { rating >= star ? 'text-brand' : 'text-white/10' }"
              onclick={() => onrate?.(star)}
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"></path>
              </svg>
            </button>
          {/each}
        </div>
      {/if}

      <div class="mb-2">
        {#if isSetMode}
          <!-- A native `range`, not the songs-mode click div below: dragging is
               the only way to land on a chosen second in a two-hour file.
               Arrow keys are overridden to ±30 s, matching the skip buttons. -->
          <input
            type="range"
            class="w-full accent-brand-blue h-1 cursor-pointer {transportLocked ? 'pointer-events-none opacity-50' : ''}"
            min="0"
            max={duration || 0}
            step="1"
            value={progress}
            disabled={transportLocked}
            oninput={(e) => onseekTo?.(Number(e.currentTarget.value))}
            onkeydown={(e) => {
              if (e.key === 'ArrowLeft') { e.preventDefault(); onskip?.(-30); }
              else if (e.key === 'ArrowRight') { e.preventDefault(); onskip?.(30); }
            }}
            aria-label={$t('player.seek')}
          />
        {:else}
          <div
            role="button"
            tabindex="0"
            class="h-1 bg-[#4d4d4d] rounded-sm cursor-pointer {transportLocked ? 'pointer-events-none opacity-50' : ''}"
            onclick={onseek}
            onkeydown={(e) => e.key === 'Enter' && onseek?.(e)}
            aria-label={$t('player.seek')}
          >
            <div class="h-full bg-white rounded-sm" style="width: {progressPercent(progress, duration)}%"></div>
          </div>
        {/if}
        <div class="flex justify-between text-[11px] text-[#b3b3b3] mt-1">
          <span>{isSetMode ? formatClock(progress) : formatTime(progress)}</span>
          <span>{isSetMode ? formatClock(duration) : formatTime(duration)}</span>
        </div>
      </div>

      <div class="flex items-center justify-between mt-2 mb-8">
        <button
          class="bg-transparent border-none p-2 cursor-pointer transition-colors {shuffleMode ? 'text-brand' : 'text-[#b3b3b3]'}"
          onclick={ontoggleShuffle}
          aria-label={$t('queue.shuffle')}
          aria-pressed={shuffleMode}
        >
          <svg viewBox="0 0 16 16" width="20" height="20" fill="currentColor">
            <path d="M13.151.922a.75.75 0 1 0-1.06 1.06L13.109 3H10.3a5 5 0 0 0-4.054 2.115L2.615 10H1.25a.75.75 0 0 0 0 1.5h2.185a5 5 0 0 0 4.054-2.115L11.121 5H13.11l-1.019 1.017a.75.75 0 1 0 1.06 1.06L15.424 4.8a.75.75 0 0 0 0-1.06L13.15 1.472a.75.75 0 0 0-.001-.55zM13.151 9.922a.75.75 0 1 0-1.06 1.06L13.109 12H11.12l-1.144-1.636a.75.75 0 1 0-1.232.862l1.378 1.968A5 5 0 0 0 14.176 13.5h.194l-1.269 1.271a.75.75 0 1 0 1.06 1.06L16.43 13.56a.75.75 0 0 0 0-1.06l-2.274-2.273a.75.75 0 0 0-1.005-.305zM5.185 3.5h1.077L7.406 5.137a.75.75 0 0 0 1.232-.863l-1.378-1.967A5 5 0 0 0 3.235 1.5H1.25a.75.75 0 0 0 0 1.5h2.185a3.5 3.5 0 0 1 2.838 1.48L5.185 3.5z"></path>
          </svg>
        </button>
        <button
          class="bg-transparent border-none p-2 cursor-pointer text-white {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}"
          onclick={onprev}
          disabled={transportLocked}
          aria-label={$t('player.previous')}
        >
          <svg viewBox="0 0 16 16" width="28" height="28" fill="currentColor">
            <path d="M3.3 1a.7.7 0 0 1 .7.7v5.15l9.95-5.744a.7.7 0 0 1 1.05.606v12.575a.7.7 0 0 1-1.05.607L4 9.15v5.15a.7.7 0 0 1-.7.7H1.7a.7.7 0 0 1-.7-.7V1.7a.7.7 0 0 1 .7-.7h1.6z"></path>
          </svg>
        </button>
        {#if isSetMode}
          <button
            class="relative bg-transparent border-none p-2 cursor-pointer text-white {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}"
            onclick={() => onskip?.(-30)}
            disabled={transportLocked}
            aria-label={$t('player.skipBack')}
          >
            <svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor" aria-hidden="true">
              <path d="M12 5V1L7 6l5 5V7a6 6 0 1 1-6 6H5a7 7 0 1 0 7-7z"></path>
            </svg>
            <span class="absolute text-[8px] font-bold top-1/2 left-1/2 -translate-x-1/2 -translate-y-[35%]">30</span>
          </button>
        {/if}
        <button
          class="w-16 h-16 bg-white rounded-full text-black flex items-center justify-center cursor-pointer transition-transform hover:scale-105 {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}"
          onclick={ontogglePlay}
          disabled={transportLocked}
          aria-label={playing ? $t('nowPlaying.pause') : $t('nowPlaying.play')}
        >
          {#if playing}
            <svg viewBox="0 0 24 24" width="28" height="28" fill="black">
              <path d="M5.7 3a.7.7 0 0 0-.7.7v16.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V3.7a.7.7 0 0 0-.7-.7H5.7zm10 0a.7.7 0 0 0-.7.7v16.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V3.7a.7.7 0 0 0-.7-.7h-2.6z"></path>
            </svg>
          {:else}
            <svg viewBox="0 0 24 24" width="28" height="28" fill="black">
              <path d="M7.05 3.606l13.49 7.788a.7.7 0 0 1 0 1.212L7.05 20.394A.7.7 0 0 1 6 19.788V4.212a.7.7 0 0 1 1.05-.606z"></path>
            </svg>
          {/if}
        </button>
        {#if isSetMode}
          <button
            class="relative bg-transparent border-none p-2 cursor-pointer text-white {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}"
            onclick={() => onskip?.(30)}
            disabled={transportLocked}
            aria-label={$t('player.skipForward')}
          >
            <svg viewBox="0 0 24 24" width="26" height="26" fill="currentColor" aria-hidden="true">
              <path d="M12 5V1l5 5-5 5V7a6 6 0 1 0 6 6h2a7 7 0 1 1-7-7z"></path>
            </svg>
            <span class="absolute text-[8px] font-bold top-1/2 left-1/2 -translate-x-1/2 -translate-y-[35%]">30</span>
          </button>
        {/if}
        <button
          class="bg-transparent border-none p-2 cursor-pointer text-white {transportLocked ? 'opacity-50 cursor-not-allowed' : ''}"
          onclick={onnext}
          disabled={transportLocked}
          aria-label={$t('player.next')}
        >
          <svg viewBox="0 0 16 16" width="28" height="28" fill="currentColor">
            <path d="M12.7 1a.7.7 0 0 0-.7.7v5.15L2.05 1.106A.7.7 0 0 0 1 1.712v12.575a.7.7 0 0 0 1.05.607L12 9.15v5.15a.7.7 0 0 0 .7.7h1.6a.7.7 0 0 0 .7-.7V1.7a.7.7 0 0 0-.7-.7h-1.6z"></path>
          </svg>
        </button>
        <button
          class="relative bg-transparent border-none p-2 cursor-pointer transition-colors {repeatMode !== 'none' ? 'text-brand' : 'text-[#b3b3b3]'}"
          onclick={ontoggleRepeat}
          aria-label={$t('player.repeat')}
        >
          <svg viewBox="0 0 16 16" width="20" height="20" fill="currentColor">
            <path d="M0 4.75A3.75 3.75 0 0 1 3.75 1h8.5A3.75 3.75 0 0 1 16 4.75v5a3.75 3.75 0 0 1-3.75 3.75H9.81l1.018 1.018a.75.75 0 1 1-1.06 1.06L6.939 12.75l2.829-2.828a.75.75 0 1 1 1.06 1.06L9.811 12h2.439a2.25 2.25 0 0 0 2.25-2.25v-5a2.25 2.25 0 0 0-2.25-2.25h-8.5A2.25 2.25 0 0 0 1.5 4.75v5A2.25 2.25 0 0 0 3.75 12H5v1.5H3.75A3.75 3.75 0 0 1 0 9.75v-5z"></path>
          </svg>
          {#if repeatMode === 'one'}
            <span class="absolute text-[8px] font-bold top-1/2 left-1/2 -translate-x-1/2 -translate-y-[60%] text-brand">1</span>
          {/if}
        </button>
      </div>

      <div class="flex items-center justify-center gap-10 mt-auto">
        {#if equalizerSupported}
          <button
            data-eq-toggle
            class="bg-transparent border-none p-2 cursor-pointer text-[#b3b3b3] hover:text-white transition-colors"
            onclick={ontoggleEqualizer}
            aria-label={$t('equalizer.title')}
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
              <path d="M4 20V14M4 10V4M12 20V12M12 8V4M20 20V16M20 12V4M1 14h6M9 8h6M17 16h6"></path>
            </svg>
          </button>
        {/if}
        <button
          class="bg-transparent border-none p-2 cursor-pointer text-[#b3b3b3] hover:text-white transition-colors"
          onclick={ontoggleQueue}
          aria-label={$t('queue.title')}
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M15 15H3v-1.5h12V15zm0-4.5H3V9h12v1.5zm0-4.5H3V4.5h12V6zm7 12l-4.5-4.5L13 18h9z"></path>
          </svg>
        </button>
      </div>
    </div>
  </div>
  {#if showLyricsSheet}
    <BottomSheet title={$t('track.lyrics')} onclose={() => (showLyricsSheet = false)}>
      <div class="px-4 pb-4 text-center space-y-3">
        {#each lyricsLines as line, i (i)}
          <p class="text-lg font-bold text-white">{line}</p>
        {/each}
      </div>
    </BottomSheet>
  {/if}
{/if}
