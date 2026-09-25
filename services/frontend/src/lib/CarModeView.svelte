<script>
  import { onMount } from 'svelte';
  import { get } from 'svelte/store';
  import { t } from './i18n/index.js';
  import { platform } from './platform/index.js';
  import { restUrl, authParams, currentTrack, playlist, playerState, favoriteGenres } from './store.js';
  import { listOf, subsonicJson } from './subsonic.js';
  import { ratings, ratingOf, tapStar } from './ratings.js';
  import { trackAfterCommand } from './nativeQueue.js';
  import { notify } from './notifications.js';
  import { startQueue } from './queue.js';

  /**
   * The driving screen, ported from the Kotlin `CarModeFragment`: everything at arm's length,
   * nothing that scrolls, big enough to aim at from behind a wheel.
   *
   * Only reachable on the native shell (see `ProfileButton.svelte`'s `platform.system.isNative`
   * guard and `App.svelte`'s `carConnected` wiring) -- a browser tab has no car to be in, and
   * `platform.player.next`/`previous` are native-only calls this view relies on.
   *
   * Transport is not reimplemented here. `togglePlay` reads and drives `platform.player`
   * directly (safe: `play`/`pause` are the same cross-shell contract `Player.svelte` uses), and
   * `next`/`previous` ask the native service to move its own queue -- the exact call the legacy
   * `CarModeFragment` made on `MediaPlayerManager` -- rather than re-deciding the next track in
   * JS, which would be a second, competing queue owner. `Player.svelte`'s existing
   * `on('command', ...)` handling (already there for a head-unit or notification press) is what
   * mirrors the move back into `currentTrack`. Duration snapshots and the mount snapshot also
   * reconcile identity, since a recovered service state need not carry a directional command.
   */

  const { onclose, onmicrophone } = $props();

  const MIX_SIZE = 50;
  const MAX_GENRE_TILES = 4;
  const MIN_GENRE_SONGS = 5;
  const FAVORITE_RATING_MIN = 4;

  let playing = $state(false);
  let genreTiles = $state([]);

  const track = $derived($currentTrack);
  const rating = $derived(ratingOf($ratings, track));
  const coverUrl = $derived(
    track?.coverArt
      ? restUrl(`/rest/getCoverArt?id=${track.coverArt}&size=300&${$authParams}`)
      : '/images/spotify-fallback.svg',
  );

  onMount(() => {
    adoptSnapshot(platform.player.state());
    const unsubscribes = [
      platform.player.on('durationchange', adoptSnapshot),
      platform.player.on('play', (state) => { playing = state.status === 'playing'; }),
      platform.player.on('pause', (state) => { playing = state.status === 'playing'; }),
      platform.player.on('timeupdate', (state) => { playing = state.status === 'playing'; }),
      platform.player.on('ended', (state) => { playing = state.status === 'playing'; }),
      platform.player.on('command', (command) => { playing = command.state.status === 'playing'; }),
    ];

    // The lock-screen behaviour the legacy screen gets for free from a navigation-destination
    // listener (see `NavigationActivity.watchCarPresence`). There is no destination change here
    // to key it off, so this view asks for it while it is mounted and releases it on the way out.
    platform.system.setKeepScreenOn({ showWhenLocked: true, turnScreenOn: true }).catch(() => {});

    loadGenreTiles();

    return () => {
      for (const unsubscribe of unsubscribes) unsubscribe();
      platform.system.setKeepScreenOn({ showWhenLocked: false, turnScreenOn: false }).catch(() => {});
    };
  });

  /** Adopt the service's identity when opening after the WebView missed a move. */
  function adoptSnapshot(state) {
    playing = state.status === 'playing';
    const moved = trackAfterCommand(get(playlist), get(currentTrack)?.id, { trackId: state.trackId });
    if (moved) currentTrack.set(moved);
  }

  /**
   * A handful of the account's own genres, favourites first -- the same source the genre browse
   * grid uses -- falling back to the library's biggest genres when nothing is starred yet, so the
   * row is never empty on a fresh account.
   */
  async function loadGenreTiles() {
    const favorites = get(favoriteGenres);
    if (Array.isArray(favorites) && favorites.length > 0) {
      genreTiles = favorites.slice(0, MAX_GENRE_TILES);
      return;
    }
    try {
      const genres = listOf(await subsonicJson('getGenres'), 'genres.genre')
        .filter((g) => Number(g.songCount) >= MIN_GENRE_SONGS)
        .sort((a, b) => b.songCount - a.songCount)
        .slice(0, MAX_GENRE_TILES)
        .map((g) => g.value);
      genreTiles = genres;
    } catch (error) {
      console.warn('Could not load the car screen\'s genre mixes', error);
      genreTiles = [];
    }
  }

  function togglePlay() {
    if (playing) platform.player.pause();
    else platform.player.play();
  }

  function skipNext() {
    platform.player.next();
  }

  function skipPrevious() {
    platform.player.previous();
  }

  /**
   * 5 means favourite; tapping the star already lit clears the rating, the same toggle every other
   * rating row uses. Goes through the shared rating store (`ratings.js`), which writes
   * optimistically and rolls back on failure, so a tap registers at once on a screen nobody should
   * be staring at to confirm it landed -- and the list behind car mode shows it too.
   *
   * @param {number} stars
   */
  function rate(stars) {
    if (!track) return;
    tapStar(track, stars);
  }

  /**
   * Starts a shuffled queue from the library, the same job the legacy `MixSeed` tiles do:
   * more of one genre, or -- for the favourites tile -- rated 4 or 5. Replaces the queue rather
   * than appending: the car screen has no view of what the queue already held, and there is no
   * bottom sheet here to check first.
   *
   * @param {string|null} genre - A genre name, or null for the favourites mix.
   */
  async function playMix(genre) {
    const params = {
      sortMethod: 'Random',
      count: MIX_SIZE,
      offset: 0,
      seed: Date.now(),
    };
    if (genre) {
      params.clusters = JSON.stringify([{ name: 'GENRE', value: [genre] }]);
    } else {
      params.ratingMin = FAVORITE_RATING_MIN;
    }
    try {
      const tracks = listOf(await subsonicJson('getSongs', params), 'songs.song');
      if (tracks.length === 0) {
        notify.error($t('notify.noRandomTracks'));
        return;
      }
      // No human name to give this one; the mix has no place of its own, so the header falls
      // back to the track's own album, same as before car mode existed.
      startQueue(tracks);
      currentTrack.set(tracks[0]);
      playerState.update((s) => ({ ...s, playing: true }));
    } catch (error) {
      console.error('Could not start the mix', error);
      notify.error($t('notify.noRandomTracks'), { detail: error.message });
    }
  }
</script>

<div class="fixed inset-0 z-50 bg-black flex flex-col text-white" data-testid="car-mode">
  <header class="flex justify-end shrink-0 p-2 pt-[max(0.5rem,env(safe-area-inset-top))]">
    <button
      class="w-14 h-14 flex items-center justify-center bg-transparent border-none text-white cursor-pointer"
      onclick={onclose}
      aria-label={$t('nowPlaying.close')}
    >
      <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor" aria-hidden="true">
        <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"></path>
      </svg>
    </button>
  </header>

  <div class="grid grid-cols-2 gap-3 px-4 shrink-0">
    <button
      class="rounded-lg bg-muma-spotify-light hover:bg-muma-spotify-highlight transition-colors text-white text-lg font-bold py-5 px-3 border-none cursor-pointer truncate"
      onclick={() => playMix(null)}
    >
      {$t('car.mixFavorites')}
    </button>
    {#each genreTiles as genre (genre)}
      <button
        class="rounded-lg bg-muma-spotify-light hover:bg-muma-spotify-highlight transition-colors text-white text-lg font-bold py-5 px-3 border-none cursor-pointer truncate"
        onclick={() => playMix(genre)}
      >
        {$t('car.mixGenre', { genre })}
      </button>
    {/each}
  </div>

  <div class="flex-1 flex items-center justify-center min-h-[96px]">
    <button
      class="w-40 h-40 rounded-full bg-brand flex items-center justify-center border-none cursor-pointer shadow-2xl"
      onclick={onmicrophone}
      aria-label={$t('car.microphone')}
    >
      <svg viewBox="0 0 24 24" width="64" height="64" fill="white" aria-hidden="true">
        <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v5a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2z"></path>
      </svg>
    </button>
  </div>

  <div class="flex items-center gap-3 px-4 mt-2">
    <img
      src={coverUrl}
      alt=""
      class="w-[72px] h-[72px] rounded object-cover shrink-0"
      onerror={(e) => e.target.src = '/images/spotify-fallback.svg'}
    />
    <div class="min-w-0 flex-1">
      <div class="text-xl font-bold truncate">{track?.title ?? $t('player.nothingPlaying')}</div>
      <div class="text-base text-muma-spotify-text truncate">{track?.artist ?? ''}</div>
    </div>
  </div>

  <div class="flex items-center justify-center gap-4 mt-4">
    <button
      class="w-20 h-20 flex items-center justify-center bg-transparent border-none text-white cursor-pointer"
      onclick={skipPrevious}
      aria-label={$t('player.previous')}
    >
      <svg viewBox="0 0 16 16" width="36" height="36" fill="currentColor">
        <path d="M3.3 1a.7.7 0 0 1 .7.7v5.15l9.95-5.744a.7.7 0 0 1 1.05.606v12.575a.7.7 0 0 1-1.05.607L4 9.15v5.15a.7.7 0 0 1-.7.7H1.7a.7.7 0 0 1-.7-.7V1.7a.7.7 0 0 1 .7-.7h1.6z"></path>
      </svg>
    </button>
    <button
      class="w-[104px] h-[104px] rounded-full bg-white text-black flex items-center justify-center border-none cursor-pointer"
      onclick={togglePlay}
      aria-label={playing ? $t('nowPlaying.pause') : $t('nowPlaying.play')}
    >
      {#if playing}
        <svg viewBox="0 0 24 24" width="40" height="40" fill="black">
          <path d="M5.7 3a.7.7 0 0 0-.7.7v16.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V3.7a.7.7 0 0 0-.7-.7H5.7zm10 0a.7.7 0 0 0-.7.7v16.6a.7.7 0 0 0 .7.7h2.6a.7.7 0 0 0 .7-.7V3.7a.7.7 0 0 0-.7-.7h-2.6z"></path>
        </svg>
      {:else}
        <svg viewBox="0 0 24 24" width="40" height="40" fill="black">
          <path d="M7.05 3.606l13.49 7.788a.7.7 0 0 1 0 1.212L7.05 20.394A.7.7 0 0 1 6 19.788V4.212a.7.7 0 0 1 1.05-.606z"></path>
        </svg>
      {/if}
    </button>
    <button
      class="w-20 h-20 flex items-center justify-center bg-transparent border-none text-white cursor-pointer"
      onclick={skipNext}
      aria-label={$t('player.next')}
    >
      <svg viewBox="0 0 16 16" width="36" height="36" fill="currentColor">
        <path d="M12.7 1a.7.7 0 0 0-.7.7v5.15L2.05 1.106A.7.7 0 0 0 1 1.712v12.575a.7.7 0 0 0 1.05.607L12 9.15v5.15a.7.7 0 0 0 .7.7h1.6a.7.7 0 0 0 .7-.7V1.7a.7.7 0 0 0-.7-.7h-1.6z"></path>
      </svg>
    </button>
  </div>

  <div class="flex items-center justify-center gap-2 py-4 mb-[env(safe-area-inset-bottom)]">
    {#each [1, 2, 3, 4, 5] as star (star)}
      <button
        class="w-12 h-12 flex items-center justify-center bg-transparent border-none cursor-pointer transition-colors {rating >= star ? 'text-brand' : 'text-white/20'}"
        onclick={() => rate(star)}
        aria-label={$t('car.rate', { star })}
        disabled={!track}
      >
        <svg viewBox="0 0 24 24" width="28" height="28" fill="currentColor">
          <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"></path>
        </svg>
      </button>
    {/each}
  </div>
</div>
