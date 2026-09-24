<script>
  import { t } from './i18n/index.js';
  import { fly } from 'svelte/transition';
  import { formatTime, formatClock, progressPercent } from './playerProgress.js';
  import BottomSheet from './BottomSheet.svelte';
  import ArtistList from './ArtistList.svelte';
  import Artwork from './Artwork.svelte';
  import MetaChips from './MetaChips.svelte';
  import TrackDetailsSheet from './TrackDetailsSheet.svelte';
  import TrackRowCompact from './TrackRowCompact.svelte';
  import { genreNames } from './genreSegments.js';
  import { playlist, queueSource } from './store.js';
  import { placeTitle, PLACE_PREFIXES } from './recentPlaces.js';
  import { viewLabel, startQueue } from './queue.js';
  import { releaseDateLabel } from './trackDate.js';
  import { describeFilter } from './management/radioChannels.js';
  import { playTrack } from './playTrack.js';
  import { listOf, subsonicJson } from './subsonic.js';
  import { primaryArtistOf } from './utils.js';
  import { loadVersions } from './versions.js';

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
    // Where `track` sits in `$playlist`, as `Player.svelte` computed it (native queue index
    // when the platform owns playback, a lookup by id otherwise) -- see technical.md section F.
    // -1 when there is nothing to point at, same as everywhere else in the app that reads a
    // queue position.
    queueIndex = -1,
    transportLocked = false,
    coverUrl = null,
    artistUrl = null,
    tint = null,
    equalizerSupported = false,
    // The output the phone plays through (`platform.system.outputRoute()`, see technical.md
    // section H), or null -- a browser tab, or a shell that has not answered yet -- which hides
    // the label entirely. Same native-only pattern as `equalizerSupported`.
    outputRoute = null,
    isSetMode = false,
    lyricsLines = [],
    // The radio: `radioActive` tints the button while a channel plays, `radioChannels` and
    // `showRadioPicker` are `Player.svelte`'s own state for the channel choice (it fetches the
    // list on the first tap and clears the flag when a channel starts), rendered here as a
    // bottom sheet because the desktop bar's dropdown has nowhere to anchor on this screen.
    radioActive = false,
    radioChannels = [],
    showRadioPicker = false,
    ontoggleRadio = null,
    onstartRadio = null,
    oncloseRadioPicker = null,
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
    onopenOutputPicker,
    onnavigate,
  } = $props();

  /**
   * One glyph per kind of output, so a glance tells a headset from the speaker before the name
   * is read. Wired and USB share the headset glyph -- both are something plugged in -- and
   * `other` falls back to the speaker's, the honest "some output" icon.
   */
  const HEADSET_ICON =
    'M12 1c-4.97 0-9 4.03-9 9v7c0 1.66 1.34 3 3 3h3v-8H5v-2c0-3.87 3.13-7 7-7s7 3.13 7 7v2h-4v8h3c1.66 0 3-1.34 3-3v-7c0-4.97-4.03-9-9-9z';
  const SPEAKER_ICON =
    'M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z';
  const OUTPUT_ICONS = {
    bluetooth:
      'M17.71 7.71 12 2h-1v7.59L6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 11 14.41V22h1l5.71-5.71-4.3-4.29 4.3-4.29zM13 5.83l1.88 1.88L13 9.59V5.83zm1.88 10.46L13 18.17v-3.76l1.88 1.88z',
    wired: HEADSET_ICON,
    usb: HEADSET_ICON,
    speaker: SPEAKER_ICON,
    other: SPEAKER_ICON,
  };

  // What the context line reads: the place the current queue was started from
  // (a genre, a playlist, an artist, ...), when `startQueue` (queue.js)
  // recorded one -- see `store.js`'s `queueSource` and
  // `docs/designs/phone-ui-polish/technical.md`, section E. Falls back to the
  // track's own album, and from there to the generic "Queue" caption, exactly
  // as before this existed.
  const playingFrom = $derived(
    $queueSource?.name ?? placeTitle({ view: $queueSource?.view }) ?? viewLabel($queueSource?.view) ?? track?.album ?? $t('queue.title'),
  );

  // The header's own tap target: the source's view when it is one of the
  // navigable kinds `recentPlaces.js` tracks (so tapping "Playing from Hardstyle"
  // opens that genre), else the track's album, same as before `queueSource` existed.
  const headerTarget = $derived(
    $queueSource?.view && PLACE_PREFIXES.some((prefix) => $queueSource.view.startsWith(prefix))
      ? $queueSource.view
      : track?.albumId
        ? `album:${track.albumId}`
        : null,
  );

  /**
   * The screen is never flat black: a vertical gradient fades from 55% of the
   * playing track's genre tint at the top into the standard dark background
   * by 60% of the way down, so the tint reads as "this screen" rather than a
   * bar of colour behind the artwork. No tint (no genre, or none the server
   * has a colour for) is the plain neutral surface, same as before this
   * existed.
   */
  const backgroundStyle = $derived(
    tint
      ? `background: linear-gradient(to bottom, color-mix(in srgb, ${tint} 55%, #121212) 0%, #121212 60%)`
      : 'background-color: #121212',
  );

  /**
   * The chip row under the artist: every genre (each its own tap target) and
   * every label -- the same two things the details sheet already renders as
   * chips, just condensed onto the player screen since it has far less room
   * than the sheet does. The release date used to sit here too; it moved
   * into the details sheet in increment B, one tap away rather than clipped
   * on a screen with no room to show it in full.
   *
   * `labels` first: that is the array LMS puts on every song node (the
   * PUBLISHER cluster). This used to read only `label`/`publisher`, which
   * nothing sets on a Subsonic song, so the label chip never rendered on the
   * player while the sheet -- which reads `labels` -- showed it fine.
   */
  const metaItems = $derived.by(() => {
    if (!track) return [];
    const items = genreNames(track.genre).map((genre) => ({ text: genre, view: `genre:${genre}` }));
    const labels = Array.isArray(track.labels) && track.labels.length
      ? track.labels.filter(Boolean)
      : [track.label || track.publisher].filter(Boolean);
    for (const label of labels) items.push({ text: label, view: `label:${label}` });
    return items;
  });

  /**
   * The player's own preview of what plays after this track (increment F).
   *
   * Shuffle empties it: the service (native) or `Player.svelte`'s own draw (browser) decides
   * the next track only when it is asked for one, so there is nothing honest to preview and
   * the section shows a line explaining that instead. Otherwise it is the three entries
   * *after* `queueIndex` by position, not by searching for the track again -- `$playlist` can
   * hold the same id twice (an album played back to back with itself, "play next" on a track
   * already queued later), and a lookup by id would always land on the first copy regardless
   * of which one is actually playing next. Wrapping to the start of the queue only happens
   * with `repeatMode === 'all'`; otherwise the preview simply runs out before three.
   */
  const nextUp = $derived.by(() => {
    if (shuffleMode) return [];
    const list = $playlist;
    if (queueIndex < 0 || list.length < 2) return [];
    const preview = [];
    for (let step = 1; step <= 3; step++) {
      let index = queueIndex + step;
      if (index >= list.length) {
        if (repeatMode !== 'all') break;
        index %= list.length;
      }
      preview.push(list[index]);
    }
    return preview;
  });

  /**
   * Jumps to a "next up" row within the queue that is already playing, rather than starting a
   * new one -- passed to `TrackRowCompact` as `onplay` so tapping a preview row does not
   * replace `$playlist`, only where `currentTrack` points into it.
   *
   * @param {object} entry
   */
  function playQueueEntry(entry) {
    playTrack(entry);
  }

  //: The artist tracks last fetched, and for which artist -- kept across an open/close so
  //: reopening the player on the same artist (the common case: skipping through their songs)
  //: does not ask the server again. `null` until the first fetch settles.
  let artistTracksRaw = $state([]);
  let fetchedArtistId = null;
  let artistFetchToken = 0;

  /**
   * "More from artist" (increment F): fetched only while the sheet is open and only for an
   * artist this has not already fetched, via the same `getSpotifyTracks` call `SongView.svelte`
   * uses for a work id, keyed by `artistId` instead. Lazy because it is the one continuation
   * section with a real network cost, and every other screen with a "more like this" already
   * defers its fetch the same way.
   */
  $effect(() => {
    const artistId = track?.artistId;
    if (!open) return; // Closed: leave any cached list alone for a reopen on the same artist.
    if (!artistId) {
      // A track (or radio) with no artist id is not "this artist, nothing found yet" -- it is
      // a different track the cached list must not leak under.
      if (fetchedArtistId !== null) {
        fetchedArtistId = null;
        artistTracksRaw = [];
      }
      return;
    }
    if (artistId === fetchedArtistId) return;
    fetchedArtistId = artistId;
    artistTracksRaw = []; // Clear the previous artist's list rather than showing it under this one while the new fetch is in flight.
    const requestToken = ++artistFetchToken;
    subsonicJson('getSpotifyTracks', { artistId, count: 7 })
      .then((data) => {
        if (requestToken !== artistFetchToken) return;
        artistTracksRaw = listOf(data, 'tracks.track');
      })
      .catch(() => {
        if (requestToken !== artistFetchToken) return;
        artistTracksRaw = [];
      });
  });

  // The current track never belongs in its own "more from" list; kept as a derived filter
  // over the raw fetch (rather than filtering once at fetch time) so a jump to a different
  // track by the same artist -- a next-up tap, one of these rows itself -- re-excludes
  // correctly without a second request.
  const moreFromArtist = $derived(
    track ? artistTracksRaw.filter((t) => String(t.id) !== String(track.id)).slice(0, 6) : [],
  );

  // The name the "more from {name}" heading uses. `track.artist` is joined text for a
  // multi-artist track ("A, B"), but the fetch above is keyed on `artistId`, which names one
  // of them -- the same "first artist" `Player.svelte`'s own `primaryArtist` picks, so the
  // heading names the artist the list is actually about rather than everyone on the credit.
  const artistName = $derived(primaryArtistOf(track)?.name ?? '');

  /**
   * Starts a fresh queue of the artist's tracks and plays the one tapped -- unlike a "next up"
   * row, this is not a jump within the current queue, it replaces it.
   *
   * @param {object} entry
   */
  function playFromArtist(entry) {
    startQueue(moreFromArtist, { name: track.artist, view: `artist:${track.artistId}` });
    playTrack(entry);
  }

  //: Every version last fetched, for `otherVersions` below. Not cached across artists/works the
  //: way `artistTracksRaw` is: a song's version list is small and cheap (`max: 6`, one request),
  //: unlike an artist's full catalogue.
  let versionsList = $state([]);
  let versionsFetchToken = 0;

  /**
   * "Other versions" (increment F): the same `loadVersions` `SongView.svelte`'s full page uses,
   * capped at a handful rather than the true count -- this is a taste, not the song page.
   * Lazy for the same reason as the artist section: only worth asking for while the sheet the
   * listener can see it in is open.
   */
  $effect(() => {
    const workId = track?.workId;
    if (!open || !workId) {
      // Bumping the token here too: a fetch still in flight when the view closed
      // must not land in the emptied list and show up on the next open.
      versionsFetchToken++;
      versionsList = [];
      return;
    }
    const requestToken = ++versionsFetchToken;
    loadVersions(workId, { max: 6 })
      .then((result) => {
        if (requestToken !== versionsFetchToken) return;
        versionsList = result;
      })
      .catch(() => {
        if (requestToken !== versionsFetchToken) return;
        versionsList = [];
      });
  });

  // The current version never belongs among its own alternatives.
  const otherVersions = $derived(
    track ? versionsList.filter((v) => String(v.id) !== String(track.id)) : [],
  );

  /**
   * Starts a queue of this song's versions and plays the one tapped.
   *
   * @param {object} entry
   */
  function playVersion(entry) {
    startQueue(versionsList, { name: track.title, view: `song:${track.workId}` });
    playTrack(entry);
  }

  let touchStartY = $state(null);
  let showLyricsSheet = $state(false);
  let showDetailsSheet = $state(false);
  // The scroll container the continuation sections (increment F) made this screen actually
  // scroll -- bound so `handleTouchEnd` can tell a swipe-to-close drag from the start of an
  // ordinary scroll through those sections. `$state` (not a plain `let`) because `bind:this`
  // writes to it after the first render, same as `Player.svelte`'s `audioElement`.
  let scrollContainerEl = $state(null);

  /**
   * Every navigation from this screen closes it first -- the chevron's own
   * `onclose` -- so a tap on a genre chip or the album never leaves the
   * full-screen player stranded over whatever it just opened.
   *
   * When `onclose` returns a promise (`closeNowPlaying` does: it consumes the
   * history entry the player pushed, and that `popstate` arrives later), the
   * navigation waits for it. Navigating first let the late `popstate` restore
   * the page underneath, so a tap on a genre or label chip landed nowhere.
   *
   * @param {string} view
   */
  function navigate(view) {
    const closing = onclose?.();
    if (closing && typeof closing.then === 'function') {
      closing.then(() => onnavigate?.(view));
    } else {
      onnavigate?.(view);
    }
  }

  function handleTouchStart(e) {
    touchStartY = e.touches?.[0]?.clientY ?? null;
  }

  /**
   * A firm downward drag on the cover closes the view, the same gesture Spotify uses. 80px is
   * well past an accidental brush or the start of a vertical scroll. Since the continuation
   * sections (increment F) made the screen scroll, the gesture only fires when the container
   * is already scrolled to the top -- otherwise a drag meant to scroll back up to the artwork
   * would close the screen instead of scrolling.
   *
   * @param {TouchEvent} e
   */
  function handleTouchEnd(e) {
    if (touchStartY === null) return;
    const endY = e.changedTouches?.[0]?.clientY ?? touchStartY;
    const delta = endY - touchStartY;
    touchStartY = null;
    if (delta > 80 && (scrollContainerEl?.scrollTop ?? 0) === 0) onclose?.();
  }

  /**
   * The queue actions the details sheet offers. Inserted by position (`queueIndex`, as
   * `Player.svelte` computed it) rather than by searching `$playlist` for the track's id: the
   * same id can appear more than once in the queue, and a search would always land on the
   * first copy regardless of which one is actually playing.
   */
  function addAfterCurrent() {
    if (!track) return;
    playlist.update((p) => {
      const newP = [...p];
      const insertAt = queueIndex >= 0 ? queueIndex + 1 : newP.length;
      newP.splice(insertAt, 0, { ...track });
      return newP;
    });
  }

  function addToEnd() {
    if (!track) return;
    playlist.update((p) => [...p, { ...track }]);
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
    class="fixed inset-0 z-40 flex flex-col text-white"
    data-testid="now-playing"
    data-tint={tint}
    style={backgroundStyle}
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
      {#if headerTarget}
        <button
          class="flex-1 min-w-0 bg-transparent border-none text-center px-2 cursor-pointer"
          onclick={() => navigate(headerTarget)}
        >
          <span class="block text-[11px] text-[#b3b3b3]">{$t('nowPlaying.playingFromLabel')}</span>
          <span class="block text-sm font-bold text-white truncate" data-testid="now-playing-context">{playingFrom}</span>
        </button>
      {:else}
        <div class="flex-1 min-w-0 text-center px-2">
          <span class="block text-[11px] text-[#b3b3b3]">{$t('nowPlaying.playingFromLabel')}</span>
          <span class="block text-sm font-bold text-white truncate" data-testid="now-playing-context">{playingFrom}</span>
        </div>
      {/if}
      <!-- The one entry point to everything else the sheet offers -- artist,
           album, play next, add to queue, lyrics (when there are any) and
           details -- replacing the lyrics-only button this header used to
           carry on its own. `now-playing-details` used to name the bottom
           row's now-removed `(i)` button; it moves here so existing tests
           and any external tooling keep the same handle on "open details". -->
      <button
        class="w-8 h-8 flex items-center justify-center text-white bg-transparent border-none cursor-pointer"
        data-testid="now-playing-details"
        onclick={() => (showDetailsSheet = true)}
        aria-label={$t('nowPlaying.more')}
      >
        <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor" aria-hidden="true">
          <path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z"></path>
        </svg>
      </button>
    </header>

    <div class="flex-1 min-h-0 overflow-y-auto overscroll-contain" bind:this={scrollContainerEl}>
      <!-- The stage: at least exactly one screen tall, so everything on it -- the transport
           above all -- is in view without scrolling, however much there is to say about the
           track. Only the artwork gives way: its box takes whatever height the text and the
           controls leave over (`flex-1 min-h-0`), and the cover is the largest square that
           fits that box. Every text line is a single line (truncated, or a scrolling chip
           row), so the height the stage needs is bounded and the controls never fall off the
           bottom -- which is what a long title, a wrapped album line or a third row of genre
           chips used to do. Only when even a zero-height cover would not make room (a phone
           on its side with a big font) does the stage grow past the screen, and the controls
           are then a scroll away rather than cut off.

           Landscape (a tablet on its side, a phone turned) splits it into two columns --
           the cover left at the full available height, text and controls right, centred
           vertically -- rather than a cover as wide as the screen and therefore far taller
           than it. `max-w-xl` keeps a portrait tablet's text column and controls at phone
           proportions instead of stretched across the whole width. -->
      <div
        class="mx-auto flex min-h-full w-full max-w-xl flex-col justify-center px-6 pb-[calc(1rem+env(safe-area-inset-bottom,0px))] landscape:grid landscape:max-w-5xl landscape:grid-cols-2 landscape:items-center landscape:gap-x-10"
        data-testid="now-playing-stage"
      >
        <!-- `role="presentation"`: the swipe-to-close gesture is a bonus on top
             of the chevron button above, which is the one thing assistive tech
             and keyboard users need -- this element carries no interactive
             semantics of its own.

             The box has no content in flow, so it only ever takes the height that is
             left. The cover sits in an absolutely positioned `container-type: size`
             layer inside it and is `min(100cqw, 100cqh)` wide: the largest square that
             fits. The layer is absolute on purpose -- as an in-flow flex item the
             container's `cqh` was resolved before `flex-grow` gave it a height, and the
             cover came out 0px wide in portrait. In portrait the box is also capped at
             the square the column's width allows (`max-w-xl` minus padding, plus the
             layer's `py-3`), and the stage centres what remains: a tall tablet otherwise
             left an empty band above and below a width-bound cover. -->
        <div
          class="relative min-h-0 flex-1 portrait:max-h-[calc(min(100vw,36rem)-1.5rem)] landscape:h-full"
          role="presentation"
          data-testid="now-playing-artwork"
          ontouchstart={handleTouchStart}
          ontouchend={handleTouchEnd}
        >
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

        <div class="flex min-w-0 flex-none flex-col" data-testid="now-playing-info">
          {#if track}
            <div class="min-w-0">
              <!-- The title opens the same details sheet as the header's menu:
                   it is the biggest thing on the screen, and "tap the title for
                   more about it" is what a listener tries first. -->
              <button
                class="block w-full truncate border-none bg-transparent p-0 text-left text-xl font-bold text-white cursor-pointer"
                data-testid="now-playing-title"
                onclick={() => (showDetailsSheet = true)}
              >{track.title}</button>
              <ArtistList artist={track.artist} artistId={track.artistId} artists={track.artists} onnavigate={navigate} size="lg" />
              <!-- Album left, release date right-aligned on the same line: the header names
                   the place the queue came from, which is not the album. The album gives
                   way (truncates) before the date does. -->
              {#if track.album || releaseDateLabel(track)}
                <div class="flex min-w-0 items-baseline gap-3 text-sm text-[#b3b3b3]" data-testid="now-playing-album-line">
                  {#if track.album}
                    {#if track.albumId}
                      <button
                        class="min-w-0 truncate border-none bg-transparent p-0 text-left text-inherit cursor-pointer hover:text-white hover:underline"
                        data-testid="now-playing-album"
                        onclick={() => navigate(`album:${track.albumId}`)}
                      >{track.album}</button>
                    {:else}
                      <span class="min-w-0 truncate">{track.album}</span>
                    {/if}
                  {/if}
                  {#if releaseDateLabel(track)}
                    <span class="ml-auto shrink-0 tabular-nums" data-testid="now-playing-date">{releaseDateLabel(track)}</span>
                  {/if}
                </div>
              {/if}
            </div>

            {#if metaItems.length > 0}
              <!-- Genres and labels on one row that scrolls sideways, never a second
                   or third row: every row the chips wrapped onto used to push the
                   transport further down, off the screen on a track with many genres. -->
              <div class="mt-3">
                <MetaChips items={metaItems} onnavigate={navigate} testid="now-playing-meta" wrap={false} />
              </div>
            {/if}

            <!-- Centred, like the transport below it, rather than hanging off the text
                 edge: left-aligned, the row read as detached from the full-width controls.
                 `max-w-xs` + `justify-between` spreads the five 44px targets evenly over a
                 fixed width, so the gaps do not balloon on a tablet. An unset star is an
                 outline in the secondary grey, not a near-invisible filled glyph: it has to
                 read as "no rating yet", not as "disabled". -->
            <div class="mx-auto mt-1 flex w-full max-w-xs items-center justify-between" data-testid="now-playing-rating">
              {#each [1, 2, 3, 4, 5] as star (star)}
                <button
                  aria-label="{star} sterren"
                  class="w-11 h-11 flex items-center justify-center bg-transparent border-none cursor-pointer transition-colors { rating >= star ? 'text-brand' : 'text-[#b3b3b3]' }"
                  data-filled={rating >= star}
                  onclick={() => onrate?.(star)}
                >
                  <svg
                    viewBox="0 0 24 24"
                    width="28"
                    height="28"
                    fill={rating >= star ? 'currentColor' : 'none'}
                    stroke="currentColor"
                    stroke-width={rating >= star ? 0 : 1.5}
                    stroke-linejoin="round"
                    aria-hidden="true"
                  >
                    <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"></path>
                  </svg>
                </button>
              {/each}
            </div>
          {/if}

          <div class="mt-2">
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
            <div class="flex justify-between text-[11px] text-[#b3b3b3] mt-1 tabular-nums">
              <span>{isSetMode ? formatClock(progress) : formatTime(progress)}</span>
              <span>{isSetMode ? formatClock(duration) : formatTime(duration)}</span>
            </div>
          </div>

          <!-- `-mx-2`: the outer buttons carry `p-2`, so without it the shuffle and repeat
               glyphs would sit 8px inside the edges every other line on the screen shares. -->
          <div class="-mx-2 mt-1 flex items-center justify-between" data-testid="now-playing-transport">
            <button
              class="bg-transparent border-none p-2 cursor-pointer transition-colors {shuffleMode ? 'text-brand' : 'text-[#b3b3b3]'}"
              onclick={ontoggleShuffle}
              aria-label={$t('queue.shuffle')}
              aria-pressed={shuffleMode}
            >
              <svg viewBox="0 0 16 16" width="24" height="24" fill="currentColor">
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
              <svg viewBox="0 0 16 16" width="24" height="24" fill="currentColor">
                <path d="M0 4.75A3.75 3.75 0 0 1 3.75 1h8.5A3.75 3.75 0 0 1 16 4.75v5a3.75 3.75 0 0 1-3.75 3.75H9.81l1.018 1.018a.75.75 0 1 1-1.06 1.06L6.939 12.75l2.829-2.828a.75.75 0 1 1 1.06 1.06L9.811 12h2.439a2.25 2.25 0 0 0 2.25-2.25v-5a2.25 2.25 0 0 0-2.25-2.25h-8.5A2.25 2.25 0 0 0 1.5 4.75v5A2.25 2.25 0 0 0 3.75 12H5v1.5H3.75A3.75 3.75 0 0 1 0 9.75v-5z"></path>
              </svg>
              {#if repeatMode === 'one'}
                <span class="absolute text-[8px] font-bold top-1/2 left-1/2 -translate-x-1/2 -translate-y-[60%] text-brand">1</span>
              {/if}
            </button>
          </div>

          <!-- The output the phone plays through (increment H, native only: `outputRoute` is
               null in a browser) on the left, the secondary actions on the right -- one row
               instead of two, so the stage stays short enough for the controls to fit. With
               no output to name, the icons centre under the transport instead. -->
          <div
            class="-mx-2 mt-3 flex items-center {outputRoute ? 'gap-2' : 'justify-center gap-10'}"
            data-testid="now-playing-actions"
          >
            {#if outputRoute}
              <button
                class="mr-auto flex min-w-0 items-center gap-2 border-none bg-transparent px-2 py-1 text-[13px] font-bold text-brand cursor-pointer"
                data-testid="now-playing-output"
                onclick={onopenOutputPicker}
                aria-label={$t('nowPlaying.outputPicker')}
              >
                <svg class="shrink-0" viewBox="0 0 24 24" width="18" height="18" fill="currentColor" aria-hidden="true">
                  <path d={OUTPUT_ICONS[outputRoute.type] ?? OUTPUT_ICONS.speaker}></path>
                </svg>
                <span class="truncate">{outputRoute.name}</span>
              </button>
            {/if}
            {#if equalizerSupported}
              <button
                data-eq-toggle
                class="shrink-0 bg-transparent border-none p-2 cursor-pointer text-[#b3b3b3] hover:text-white transition-colors"
                onclick={ontoggleEqualizer}
                aria-label={$t('equalizer.title')}
              >
                <!-- A filled bar-chart glyph, not the stroked one this button used
                     before increment B -- it now sits next to solid icons
                     (versions, queue) at the same 24px, and a stroke read as a
                     lighter weight than either. -->
                <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" aria-hidden="true">
                  <path d="M10 20h4V4h-4v16zm-6 0h4v-8H4v8zm12-11v11h4V9h-4z"></path>
                </svg>
              </button>
            {/if}
            {#if ontoggleRadio}
              <button
                class="shrink-0 bg-transparent border-none p-2 cursor-pointer transition-colors hover:text-white {radioActive ? 'text-[#b266ff]' : 'text-[#b3b3b3]'}"
                data-testid="now-playing-radio"
                onclick={ontoggleRadio}
                aria-label={$t('player.radio')}
                aria-pressed={radioActive}
              >
                <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" aria-hidden="true">
                  <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm0 4a6 6 0 1 1 0 12 6 6 0 0 1 0-12zm0 4a2 2 0 1 0 0 4 2 2 0 0 0 0-4z"></path>
                </svg>
              </button>
            {/if}
            {#if track?.workId}
              <button
                class="shrink-0 bg-transparent border-none p-2 cursor-pointer text-[#b3b3b3] hover:text-white transition-colors"
                data-testid="now-playing-song"
                onclick={() => navigate(`song:${track.workId}`)}
                aria-label={$t('track.versions')}
              >
                <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor" aria-hidden="true">
                  <path d="M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h10v2H4v-2z"></path>
                </svg>
              </button>
            {/if}
            <button
              class="shrink-0 bg-transparent border-none p-2 cursor-pointer text-[#b3b3b3] hover:text-white transition-colors"
              onclick={ontoggleQueue}
              aria-label={$t('queue.title')}
            >
              <svg viewBox="0 0 24 24" width="24" height="24" fill="currentColor">
                <path d="M15 15H3v-1.5h12V15zm0-4.5H3V9h12v1.5zm0-4.5H3V4.5h12V6zm7 12l-4.5-4.5L13 18h9z"></path>
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- The continuation sections (increment F): what plays after this, more from the same
           artist, and this song's other files -- below the stage, one scroll down, never
           competing with the controls for the first screen. Each is independently hidden
           when it has nothing to show, so a track with no `workId` and no queue after it
           renders none of this at all rather than three empty headings. Their rows navigate
           through `navigate`, like everything else here, so the player closes first. -->
      <div class="mx-auto flex w-full max-w-xl flex-col gap-6 px-6 pt-4 pb-[calc(1.5rem+env(safe-area-inset-bottom,0px))] landscape:max-w-5xl">
        {#if shuffleMode || nextUp.length > 0}
          <section>
            <h3 class="text-base font-bold mb-3">{$t('nowPlaying.nextUp')}</h3>
            {#if shuffleMode}
              <p class="text-sm text-[#b3b3b3]">{$t('nowPlaying.shuffleOn')}</p>
            {:else}
              <div class="flex flex-col gap-1">
                {#each nextUp as entry, i (i)}
                  <TrackRowCompact track={entry} onnavigate={navigate} onplay={() => playQueueEntry(entry)} />
                {/each}
              </div>
            {/if}
          </section>
        {/if}

        {#if moreFromArtist.length > 0}
          <section>
            <div class="flex items-center justify-between mb-3">
              <h3 class="text-base font-bold">{$t('nowPlaying.moreFrom', { name: artistName })}</h3>
              <button
                class="bg-transparent border-none p-0 text-sm text-[#b3b3b3] hover:text-white hover:underline cursor-pointer"
                onclick={() => navigate(`artist:${track.artistId}`)}
              >
                {$t('dashboard.showAll')}
              </button>
            </div>
            <div class="flex flex-col gap-1">
              {#each moreFromArtist as entry (entry.id)}
                <TrackRowCompact track={entry} onnavigate={navigate} onplay={() => playFromArtist(entry)} />
              {/each}
            </div>
          </section>
        {/if}

        {#if otherVersions.length > 0}
          <section>
            <h3 class="text-base font-bold mb-3">{$t('track.versions')}</h3>
            <div class="flex flex-col gap-1">
              {#each otherVersions as entry (entry.id)}
                <TrackRowCompact track={entry} onnavigate={navigate} onplay={() => playVersion(entry)} />
              {/each}
            </div>
          </section>
        {/if}
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
  {#if showRadioPicker}
    <BottomSheet title={$t('radio.chooseChannel')} onclose={() => oncloseRadioPicker?.()}>
      <div class="flex flex-col" role="menu" data-testid="now-playing-radio-picker">
        {#each radioChannels as channel (channel.slug)}
          <button
            class="w-full text-left px-4 py-3 bg-transparent border-none cursor-pointer text-white hover:bg-white/10 transition-colors"
            role="menuitem"
            onclick={() => onstartRadio?.(channel)}
          >
            <span class="block text-sm font-bold">{channel.name}</span>
            <span class="block text-[12px] text-[#b3b3b3]">{describeFilter(channel.filter, $t('management.radio.wholeLibrary'))}</span>
          </button>
        {/each}
      </div>
    </BottomSheet>
  {/if}

  {#if showDetailsSheet && track}
    <TrackDetailsSheet
      {track}
      {rating}
      {onrate}
      hasLyrics={lyricsLines.length > 0}
      onclose={() => (showDetailsSheet = false)}
      onnavigate={navigate}
      durationLabel={isSetMode ? formatClock(duration) : formatTime(duration)}
      onlyrics={() => { showDetailsSheet = false; showLyricsSheet = true; }}
      onplaynext={() => { addAfterCurrent(); showDetailsSheet = false; }}
      onaddqueue={() => { addToEnd(); showDetailsSheet = false; }}
    />
  {/if}
{/if}
