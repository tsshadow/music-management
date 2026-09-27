<script>
  import { openSong, pressEntity, seedFromTrack } from './entitySeeds.js';
  import { t, locale } from './i18n/index.js';
  import { currentTrack, playerState, authParams, playlist, isMobile, trackListLines, highlightedTrackId, mumaApiUrl, restUrl, showConfirmationDialog } from './store.js';
  import { startQueue } from './queue.js';
  import ArtistList from './ArtistList.svelte';
  // Opened from a row's menu or a long press, never on the first screen: its own chunk
  // (lazyViews.js, issue #114).
  import LazyView from './LazyView.svelte';
  import Modal from './Modal.svelte';
  import { notify } from './notifications.js';
  import { releaseDateLabel } from './trackDate.js';
  import { genreSegments } from './genreSegments.js';
  import { platform as defaultPlatform } from './platform/index.js';
  import { FALLBACK, artistImageFallback, coverArtSrc, localCoverArt, resolveCoverArt } from './coverArt.js';
  import Artwork from './Artwork.svelte';
  import { offline } from './subsonic.js';
  import { formatBytes, isSet, trackSize } from './downloads.js';
  import { formatHoursMinutes } from './playerProgress.js';
  import { logAction } from './diagnosticsLog.js';
  import { ratings, ratingOf as ratingFor, tapStar } from './ratings.js';

  const {
    tracks = [],
    isQueue = false,
    playlistId = null,
    onremove = null,
    onnavigate,
    showDate = false,
    // The name the player header gives this list when a row starts a queue from it ("Nummers ·
    // Recent uitgebracht"); null lets `startQueue` name the current view itself.
    sourceName = null,
    // For a paged list (a feed, the songs list, a preset, search, ...): where the list continues,
    // a `{kind, cursor, fetchNext}` continuation (`listContinuation.js`), handed to `startQueue` so
    // a queue started by tapping a row tops itself up like one started with the play button
    // (docs/designs/list-continuation/). Null for a list that is whole.
    continuation = null,
    platform = defaultPlatform
  } = $props();

  /**
   * What is downloaded, for the rows on screen.
   *
   * One `stateOf` per rendered list rather than one per row -- that is the
   * whole reason the plugin takes a batch -- refreshed from the `progress`
   * event, which is the only thing that can change an answer while the list is
   * up. In a browser `supported` is false, nothing is asked, and every row
   * renders exactly as it did before this feature existed.
   */
  /**
   * The row's cover, or `null` when there is none: `coverArtSrc` answers a missing or
   * unresolved cover with `FALLBACK` (the MuMa mark), while `Artwork` wants `null` so it
   * can fall through to the artist portrait and then to its own panel. Same mapping
   * `TrackCard` and `TrackRowCompact` make.
   *
   * The panel is left titleless here, unlike in a card: at 48 pixels, directly beside the
   * row's own title, a second copy of that title is unreadable noise rather than the
   * identification it is on a square tile.
   */
  function thumbnailFor(track) {
    const src = coverArtSrc(track.coverArt, 48, $authParams, $localCoverArt, $offline);
    return src === FALLBACK ? null : src;
  }

  const downloadsSupported = $derived(platform?.storage?.supported === true);
  let downloadStates = $state({});
  /** The set whose size is being confirmed, or null. */
  let pendingSet = $state(null);

  const trackIds = $derived(tracks.map((track) => String(track.id)));

  async function refreshDownloadStates() {
    if (!downloadsSupported || trackIds.length === 0) return;
    try {
      downloadStates = await platform.storage.stateOf(trackIds);
    } catch (e) {
      console.warn('Could not read the download states for this list', e);
    }
  }

  $effect(() => {
    // Reads `trackIds` so a new list is asked about; the call itself is not
    // reactive, so nothing here loops.
    void trackIds;
    refreshDownloadStates();
  });

  $effect(() => {
    if (!downloadsSupported) return;
    return platform.storage.onProgress((event) => {
      if (!trackIds.includes(String(event.id))) return;
      downloadStates = { ...downloadStates, [String(event.id)]: event.state };
    });
  });

  // Offline, the artwork comes off the device; online this resolves nothing.
  $effect(() => {
    void $offline;
    resolveCoverArt(tracks.map((track) => track.coverArt), platform);
  });

  /**
   * @param {Object} track
   * @returns {string} One of none/queued/running/done/failed.
   */
  function downloadStateOf(track) {
    return downloadStates[String(track.id)] ?? 'none';
  }

  /**
   * Starts a download, asking first when it is a set.
   *
   * The size line before a set is the functional design's own requirement: a
   * two-hour recording is hundreds of megabytes and a tap should not spend them
   * silently. Short tracks start straight away -- a confirmation per three
   * minute song would be noise.
   *
   * @param {Event} e
   * @param {Object} track
   */
  function download(e, track) {
    e.stopPropagation();
    if (isSet(track) && $showConfirmationDialog) {
      pendingSet = track;
      return;
    }
    start(track);
  }

  /**
   * @param {Object} track
   */
  async function start(track) {
    pendingSet = null;
    downloadStates = { ...downloadStates, [String(track.id)]: 'queued' };
    logAction('download.start', { trackId: track.id });
    try {
      await platform.storage.download([String(track.id)], { pin: true });
    } catch (err) {
      console.error('Could not start a download', err);
      notify.error($t('downloads.startFailed'), { detail: err.message });
      await refreshDownloadStates();
    }
  }

  /**
   * @param {Event} e
   * @param {Object} track
   */
  async function removeDownload(e, track) {
    e.stopPropagation();
    logAction('download.cancel', { trackId: track.id });
    try {
      await platform.storage.remove([String(track.id)]);
      downloadStates = { ...downloadStates, [String(track.id)]: 'none' };
    } catch (err) {
      console.error('Could not remove a download', err);
      notify.error($t('downloads.removeFailed'), { detail: err.message });
    }
  }

  /** The selected row stays independent of playback while its details are open. */
  let detailsTrack = $state(null);
  let detailsIndex = $state(-1);

  /** Close before navigating so the sheet never covers the destination. */
  function detailsNavigate(view) {
    detailsTrack = null;
    onnavigate?.(view);
  }

  let selectedLyricsTrack = $state(null);
  let lyricsLines = $state([]);
  let isLoadingLyrics = $state(false);

  /**
   * Fetches and shows lyrics for a track.
   *
   * @param {Event} e - The click event.
   * @param {Object} track - The track object.
   */
  async function showLyrics(e, track) {
      e.stopPropagation();
      selectedLyricsTrack = track;
      lyricsLines = [];
      isLoadingLyrics = true;
      try {
          const response = await fetch(restUrl(`/rest/getLyricsBySongId?id=${track.id}&${$authParams}`));
          const data = await response.json();
          const structuredLyrics = data['subsonic-response']?.lyricsList?.structuredLyrics;
          if (structuredLyrics) {
              const lyrics = Array.isArray(structuredLyrics) ? structuredLyrics[0] : structuredLyrics;
              if (lyrics && lyrics.line) {
                  lyricsLines = Array.isArray(lyrics.line) ? lyrics.line : [lyrics.line];
              }
          }
      } catch (err) {
          console.error("Failed to fetch lyrics:", err);
      } finally {
          isLoadingLyrics = false;
      }
  }

  /**
   * Formats a date string to a more readable format.
   *
   * @param {string} dateStr - The date string from the backend.
   * @returns {string} The formatted date.
   */
  function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
      const date = new Date(dateStr);
      return date.toLocaleString();
    } catch (e) {
      return dateStr;
    }
  }

  /**
   * The rating to show for a track: the shared rating store (`ratings.js`), so a rating set in
   * the player, Now Playing or car mode repaints this row too, else what the backend sent.
   *
   * @param {Object} track - The track object.
   * @returns {number} The rating, 0 when unrated.
   */
  function ratingOf(track) {
    return ratingFor($ratings, track);
  }

  /**
   * A tap on star `rating` for a track: sets it, or clears it when it is already that many stars.
   *
   * @param {Object} track - The track object.
   * @param {number} rating - The star tapped (1-5).
   */
  function updateRating(track, rating) {
    return tapStar(track, rating);
  }

  /**
   * Sets the current track and starts playback.
   * If not in queue mode, also updates the global playlist.
   *
   * Whatever page rendered this list (a genre, an artist, a playlist, ...)
   * is already the current view, and `startQueue`'s default `view` picks
   * that up on its own -- see `queue.js`. `sourceName` is for the pages
   * whose view name says too little on its own: the whole songs list is
   * "Nummers", but what plays is "Nummers · Recent uitgebracht".
   *
   * @param {Object} track - The track object to play.
   */
  function playTrack(track) {
    currentTrack.set(track);
    if (!isQueue) {
        startQueue(tracks, { name: sourceName, continuation });
    }
    playerState.update(s => ({ ...s, playing: true }));
  }

  /**
   * Removes a track from the playlist by its index.
   *
   * @param {Event} e - The click event.
   * @param {number} index - The index of the track in the playlist.
   */
  function removeTrack(e, index) {
      e.stopPropagation();
      if (isQueue) {
          playlist.update(p => {
              const newP = [...p];
              newP.splice(index, 1);
              return newP;
          });
      }
      if (onremove) {
          onremove(index);
      }
  }

  /**
   * Moves a track up or down in the playlist.
   *
   * @param {Event} e - The click event.
   * @param {number} index - The current index of the track.
   * @param {number} direction - The direction to move (-1 for up, 1 for down).
   */
  function moveTrack(e, index, direction) {
      e.stopPropagation();
      playlist.update(p => {
          const newP = [...p];
          const newIndex = index + direction;
          if (newIndex < 0 || newIndex >= newP.length) return newP;
          [newP[index], newP[newIndex]] = [newP[newIndex], newP[index]];
          return newP;
      });
  }

  /**
   * Adds a track to the playlist immediately after the current track.
   *
   * @param {Event} e - The click event.
   * @param {Object} track - The track to add.
   */
  function addAfterCurrent(e, track) {
      e.stopPropagation();
      playlist.update(p => {
          const newP = [...p];
          const currentIndex = newP.findIndex(t => String(t.id) === String($currentTrack?.id));
          if (currentIndex === -1) {
              newP.push({ ...track });
          } else {
              newP.splice(currentIndex + 1, 0, { ...track });
          }
          return newP;
      });
  }

  /**
   * Adds a track to the end of the current playlist.
   *
   * @param {Event} e - The click event.
   * @param {Object} track - The track to add.
   */
  function addToEnd(e, track) {
      e.stopPropagation();
      playlist.update(p => [...p, { ...track }]);
  }

  /**
   * Triggers a metadata refresh for a track via MuMa.
   *
   * @param {Event} e - The click event.
   * @param {Object} track - The track object to refresh.
   */
  async function refreshTrack(e, track) {
      e.stopPropagation();
      if (!confirm($t('track.confirmRefresh', { title: track.title }))) return;
      
      try {
          const response = await fetch(`${$mumaApiUrl}/api/tracks/${track.id}/refresh?${$authParams}`, {
              method: 'POST'
          });
          if (response.ok) {
              notify.success($t('notify.trackRefreshed'));
          } else {
              const data = await response.json().catch(() => ({}));
              notify.error($t('notify.trackRefreshFailed'), {
                  detail: data.detail || response.statusText,
              });
          }
      } catch (e) {
          console.error("Failed to refresh track:", e);
          notify.error($t('notify.trackRefreshFailed'), { detail: e.message });
      }
  }

  /**
   * Formats milliseconds into a "M:SS" string.
   *
   * @param {number} ms - Time in milliseconds.
   * @returns {string} Formatted time string.
   */
  function formatTime(ms) {
    if (!ms) return "0:00";
    const minutes = Math.floor(ms / 60000);
    const seconds = ((ms % 60000) / 1000).toFixed(0);
    return minutes + ":" + (seconds < 10 ? '0' : '') + seconds;
  }

  /**
   * The duration column's text for one row: "h:mm" for a set -- the design's
   * own call, worth the space a two-hour recording actually needs -- and the
   * existing "M:SS" for a plain track. Decided per row on the track's own
   * duration rather than on `viewMode`, so a mixed list (history, search)
   * never shows the wrong format for what a row actually is.
   *
   * @param {Object} track
   * @returns {string}
   */
  function durationCellText(track) {
    return isSet(track) ? formatHoursMinutes(track.duration) : formatTime(track.duration * 1000);
  }


  $effect(() => {
    if ($highlightedTrackId) {
      // Use a small timeout to ensure the DOM is updated if tracks just loaded
      setTimeout(() => {
        const element = document.querySelector(`[data-track-id="${$highlightedTrackId}"]`);
        if (element) {
          element.scrollIntoView({ behavior: 'smooth', block: 'center' });
          // Clear highlight after 3 seconds
          setTimeout(() => highlightedTrackId.set(null), 3000);
        }
      }, 100);
    }
  });
</script>

<!-- table-fixed: the title cell holds nowrap text, and under the default auto layout that
     text sets the column's minimum width, so a long title pushed the table past the phone's
     viewport and the whole page scrolled sideways. Fixed layout gives the title column what
     is left after the sized columns and lets `truncate` do its work.

     The optional columns appear by the width of the table itself (`@container`, `@xl:` ...),
     not by the viewport (`md:`/`lg:`): on a tablet the sidebar takes a quarter of the screen,
     so a viewport breakpoint switched on album, genres, date, plays and rating for a table
     only ~500px wide, and the title was left ~65px -- "TITANI..." with the artist spilling
     over the album column. Each column now joins only once the table has room for it, and
     the title keeps what is left. Touch devices never get the rating column: their stars
     sit under the artist, so the column stayed empty there. -->
<div class="@container w-full">
<table class="w-full table-fixed border-collapse text-muma-spotify-text text-sm">
  <thead class="border-b border-white/10">
    <tr>
      <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-[50px] text-right hidden @2xl:table-cell">#</th>
      <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em]">{#if !$isMobile}{$t('track.title')}{/if}</th>
      {#if !isQueue}
        <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-[26%] hidden @xl:table-cell">{$t('common.album')}</th>
        <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-[18%] hidden @3xl:table-cell">{$t('nav.genres')}</th>
        <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-28 hidden @2xl:table-cell">{$t('track.date')}</th>
        <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-16 hidden @5xl:table-cell text-center">{$t('track.plays')}</th>
        {#if !$isMobile}
          <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-32 hidden @4xl:table-cell text-center">{$t('filter.rating')}</th>
        {/if}
      {/if}
      <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] w-[56px] @2xl:w-[88px] text-right">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" class="inline">
          <path d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM0 8a8 8 0 1116 0A8 8 0 010 8z"></path>
          <path d="M8 4a.5.5 0 01.5.5v3h3a.5.5 0 010 1H8a.5.5 0 01-.5-.5v-4A.5.5 0 018 4z"></path>
        </svg>
      </th>
      <!-- Phone rows reserve one touch target for the details sheet; desktop keeps hover actions. -->
      <th class="text-left p-2 px-4 font-normal uppercase text-[11px] tracking-[0.1em] text-center {$isMobile ? (isQueue || playlistId ? 'w-[84px]' : 'w-[48px]') : isQueue || playlistId ? 'w-[84px] md:w-[100px]' : 'w-[48px] md:w-[100px]'}"></th>
    </tr>
  </thead>
  <tbody>
    {#each tracks as track, i (track.id + '-' + i)}
      <tr
        role="button"
        tabindex="0"
        data-track-id={track.id}
        class="group hover:bg-white/10 active:bg-white/5 hover:text-white h-14 md:h-16 cursor-pointer select-none {String($currentTrack?.id) === String(track.id) ? 'text-brand' : ''} {String($highlightedTrackId) === String(track.id) ? 'bg-brand/20 text-white' : ''}"
        onclick={() => { if ($isMobile) playTrack(track); }}
        ondblclick={() => { if (!$isMobile) playTrack(track); }}
        onkeydown={(e) => e.target === e.currentTarget && e.key === 'Enter' && playTrack(track)}
      >
        <td class="p-2 px-4 text-right relative hidden @2xl:table-cell">
            <span class="block group-hover:hidden">{i + 1}</span>
            <button
              aria-label={$t('common.play')}
              class="hidden group-hover:block bg-transparent border-none text-white cursor-pointer p-0 absolute right-4 top-1/2 -translate-y-1/2"
              onclick={() => playTrack(track)}
            >
                <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                    <path d="M7 6v12l10-6z"></path>
                </svg>
            </button>
        </td>
        <td class="p-2 px-4">
          <div class="flex items-center gap-3">
            <!-- The same cover -> artist portrait -> tinted panel chain the cards, the
                 compact rows and the player use. This table drew a bare `<img>` whose
                 `onerror` went straight to the MuMa mark, so the artist fallback that
                 shipped with the cards never reached the one list most tracks are played
                 from -- and with 387 of 149.626 SoundCloud files carrying artwork, that is
                 a column of identical placeholders. -->
            <Artwork
              class="w-12 h-12 shrink-0"
              coverUrl={thumbnailFor(track)}
              artistUrl={$offline ? null : artistImageFallback(track, $authParams)}
              title=""
              alt=""
            />
            <div class="flex flex-col min-w-0">
              <span class="text-sm md:text-base font-medium truncate {String($currentTrack?.id) === String(track.id) ? 'text-brand' : 'text-white'}">
                {track.title}
                {#if downloadStateOf(track) !== 'none'}
                  {@const state = downloadStateOf(track)}
                  <span
                    class="inline-block align-middle ml-1.5 {state === 'failed' ? 'text-red-400' : state === 'done' ? 'text-brand' : 'text-muma-spotify-text'}"
                    aria-label={$t(`downloads.state.${state}`)}
                    title={$t(`downloads.state.${state}`)}
                    data-testid="download-glyph"
                    data-state={state}
                  >
                    {#if state === 'done'}
                      <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-1 14.4L6.6 12 8 10.6l3 3 5-5L17.4 10 11 16.4z"></path></svg>
                    {:else if state === 'failed'}
                      <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"></path></svg>
                    {:else}
                      <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor" class={state === 'running' ? 'animate-pulse' : ''}><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"></path></svg>
                    {/if}
                  </span>
                {/if}
              </span>
              <!-- `truncate` on a wrapper: the names are inline text, and one long
                   unbroken credit ("Bössels,Revellers") otherwise ran on over the
                   album column next to it. -->
              <div class="min-w-0 truncate">
                <ArtistList
                  artist={track.artist}
                  artistId={track.artistId}
                  artists={track.artists}
                  active={String($currentTrack?.id) === String(track.id)}
                  onnavigate={onnavigate}
                />
              </div>
              {#if $isMobile && Number($trackListLines) === 3}
                <div class="text-xs text-muma-spotify-text truncate" data-testid="track-third-line">
                  {#if track.albumId}
                    <button class="bg-transparent border-none p-0 text-inherit hover:underline cursor-pointer" onpointerdown={() => pressEntity('album', { id: track.albumId })} onclick={(e) => { e.stopPropagation(); seedFromTrack(track); onnavigate?.(`album:${track.albumId}`); }}>{track.album || ''}</button>
                  {:else}{track.album || ''}{/if}
                  {#if track.album} • {/if}{showDate ? formatDate(track.listenedAt) : releaseDateLabel(track)}
                </div>
              {/if}
              {#if $isMobile && !isQueue}
                <!-- The phone has no hover state to reveal the desktop rating
                     column (`hidden lg:table-cell` below), so a touch device
                     gets its own copy under the artist instead of losing
                     rating access entirely. -->
                <div class="flex gap-0.5 mt-0.5" data-testid="mobile-rating">
                  {#each [1, 2, 3, 4, 5] as star (star)}
                    <button
                      aria-label="{star} sterren"
                      class="bg-transparent border-none p-0.5 cursor-pointer transition-colors { ratingOf(track) >= star ? 'text-brand' : 'text-white/20' }"
                      onclick={(e) => { e.stopPropagation(); updateRating(track, star); }}
                    >
                      <svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor">
                        <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"></path>
                      </svg>
                    </button>
                  {/each}
                </div>
              {/if}
            </div>
          </div>
        </td>
        {#if !isQueue}
          <td class="p-2 px-4 hidden @xl:table-cell truncate" title={track.album || ''}>
            <span
              role="link"
              tabindex="0"
              class="hover:underline cursor-pointer"
              onpointerdown={() => pressEntity('album', { id: track.albumId })}
              onclick={() => { seedFromTrack(track); onnavigate?.(`album:${track.albumId}`); }}
              onkeydown={(e) => { if (e.key === 'Enter') { seedFromTrack(track); onnavigate?.(`album:${track.albumId}`); } }}
            >{track.album || ''}</span>
          </td>
          <td class="p-2 px-4 text-xs italic opacity-80 truncate hidden @3xl:table-cell" title={track.genre || ''}>
            {#each genreSegments(track.genre) as segment, i (i)}{#if segment.name}<span
                role="link"
                tabindex="0"
                class="hover:underline cursor-pointer"
                onclick={(e) => { e.stopPropagation(); if (onnavigate) onnavigate(`genre:${segment.name}`); }}
                onkeydown={(e) => { if (e.key === 'Enter') { e.stopPropagation(); if (onnavigate) onnavigate(`genre:${segment.name}`); } }}
              >{segment.text}</span>{:else}{segment.text}{/if}{/each}
          </td>
          <td class="p-2 px-4 hidden @2xl:table-cell whitespace-nowrap tabular-nums">
            {#if showDate}
              {formatDate(track.listenedAt)}
            {:else}
              {releaseDateLabel(track)}
            {/if}
          </td>
          <td class="p-2 px-4 hidden @5xl:table-cell text-center text-xs opacity-70">
            {track.globalPlayCount || ''}
          </td>
          {#if !$isMobile}
          <td class="p-2 px-4 hidden @4xl:table-cell">
              <div class="flex gap-0.5 justify-center">
                {#each [1, 2, 3, 4, 5] as star (star)}
                  <button
                    aria-label="{star} sterren"
                    class="bg-transparent border-none p-0.5 cursor-pointer transition-colors { ratingOf(track) >= star ? 'text-brand' : 'text-white/10 hover:text-white/30' }"
                    onclick={(e) => { e.stopPropagation(); updateRating(track, star); }}
                  >
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                      <path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"></path>
                    </svg>
                  </button>
                {/each}
              </div>
          </td>
          {/if}
        {/if}
        <td class="p-2 px-4 text-right text-xs md:text-sm whitespace-nowrap tabular-nums">{durationCellText(track)}</td>
        <td class="p-1 md:px-4 text-center">
          {#if $isMobile}
            <button class="w-10 h-10 bg-transparent border-none text-white text-xl cursor-pointer" aria-label={$t('track.details')} onclick={(e) => { e.stopPropagation(); detailsIndex = i; detailsTrack = track; }}>⋯</button>
          {/if}
          <!-- Hover-only actions: a touch screen has no hover to reveal them, and on a tablet
               (`md` by viewport) they took 100px of invisible width from the title. -->
          <div class="{$isMobile ? 'hidden' : 'hidden md:flex'} gap-1 justify-center md:opacity-0 md:group-hover:opacity-100 transition-opacity">
              {#if isQueue}
                      <button
                        aria-label={$t('track.moveUp')}
                        title={$t('track.moveUp')}
                        class="hidden md:flex bg-transparent border-none text-muma-spotify-text cursor-pointer p-1 items-center justify-center rounded hover:bg-muma-spotify-hover hover:text-white disabled:text-[#555] disabled:cursor-not-allowed"
                        onclick={(e) => moveTrack(e, i, -1)}
                        disabled={i === 0}
                      >
                          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                              <path d="M7 14l5-5 5 5z"></path>
                          </svg>
                      </button>
                      <button
                        aria-label={$t('track.moveDown')}
                        title={$t('track.moveDown')}
                        class="hidden md:flex bg-transparent border-none text-muma-spotify-text cursor-pointer p-1 items-center justify-center rounded hover:bg-muma-spotify-hover hover:text-white disabled:text-[#555] disabled:cursor-not-allowed"
                        onclick={(e) => moveTrack(e, i, 1)}
                        disabled={i === tracks.length - 1}
                      >
                          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                              <path d="M7 10l5 5 5-5z"></path>
                          </svg>
                      </button>
              {/if}

              {#if isQueue || playlistId}
                  <button
                    aria-label={$t('common.remove')}
                    title={$t('common.remove')}
                    class="bg-transparent border-none text-muma-spotify-text cursor-pointer p-1 flex items-center justify-center rounded hover:bg-muma-spotify-hover hover:text-white hover:text-pink-500"
                    onclick={(e) => removeTrack(e, i)}
                  >
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                          <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z"></path>
                      </svg>
                  </button>
              {/if}

              {#if !isQueue}
                  <button
                    aria-label={$t('track.reload')}
                    title={$t('track.reload')}
                    class="bg-transparent border-none text-muma-spotify-text cursor-pointer p-1 flex items-center justify-center rounded hover:bg-muma-spotify-hover hover:text-white"
                    onclick={(e) => refreshTrack(e, track)}
                  >
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                          <path d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"></path>
                      </svg>
                  </button>
                  <button
                    aria-label={$t('track.playNext')}
                    title={$t('track.playNext')}
                    class="bg-transparent border-none text-muma-spotify-text cursor-pointer p-1 flex items-center justify-center rounded hover:bg-muma-spotify-hover hover:text-white"
                    onclick={(e) => addAfterCurrent(e, track)}
                  >
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                          <path d="M13 13h5v2h-5v5h-2v-5H6v-2h5V8h2v5z"></path>
                          <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"></path>
                      </svg>
                  </button>
                  <button
                    aria-label={$t('track.addToQueue')}
                    title={$t('track.addToQueue')}
                    class="bg-transparent border-none text-muma-spotify-text cursor-pointer p-1 flex items-center justify-center rounded hover:bg-muma-spotify-hover hover:text-white"
                    onclick={(e) => addToEnd(e, track)}
                  >
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                          <path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"></path>
                      </svg>
                  </button>
              {/if}

              {#if track.workId}
                <button
                  aria-label={$t('track.versions')}
                  title={$t('track.versions')}
                  class="hidden md:flex bg-transparent border-none text-muma-spotify-text cursor-pointer p-1 items-center justify-center rounded hover:bg-muma-spotify-hover hover:text-white"
                  onclick={(e) => { e.stopPropagation(); openSong(onnavigate, track); }}
                >
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                        <path d="M4 6h16v2H4V6zm0 5h16v2H4v-2zm0 5h10v2H4v-2z"></path>
                    </svg>
                </button>
              {/if}

              <button
                aria-label={$t('track.lyrics')}
                title={$t('track.lyrics')}
                class="hidden md:flex bg-transparent border-none text-muma-spotify-text cursor-pointer p-1 items-center justify-center rounded hover:bg-muma-spotify-hover hover:text-white"
                onclick={(e) => showLyrics(e, track)}
              >
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                      <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"></path>
                  </svg>
              </button>

              {#if downloadsSupported}
                <!-- Keeping the file on this device, which is not the browser's
                     "save a copy" below: the two live side by side because they
                     do different things, and only one of them exists here. -->
                {#if downloadStateOf(track) === 'none' || downloadStateOf(track) === 'failed'}
                  <button
                    aria-label={$t('downloads.download')}
                    title={$t('downloads.download')}
                    class="bg-transparent border-none text-muma-spotify-text cursor-pointer p-1 flex items-center justify-center rounded hover:bg-muma-spotify-hover hover:text-white"
                    onclick={(e) => download(e, track)}
                  >
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                          <path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 11.2V16h-2v-2.8L8.4 15 7 13.6 12 9l5 4.6-1.4 1.4L13 13.2z" transform="rotate(180 12 12)"></path>
                      </svg>
                  </button>
                {:else}
                  <button
                    aria-label={$t('downloads.remove')}
                    title={$t('downloads.remove')}
                    class="bg-transparent border-none text-brand cursor-pointer p-1 flex items-center justify-center rounded hover:bg-muma-spotify-hover hover:text-white"
                    onclick={(e) => removeDownload(e, track)}
                  >
                      <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                          <path d="M6 19c0 1.1.9 2 2 2h8a2 2 0 0 0 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"></path>
                      </svg>
                  </button>
                {/if}
              {/if}

              <a
                href={restUrl(`/rest/download?id=${track.id}&${$authParams}`)}
                download={`${track.artist} - ${track.title}.mp3`}
                aria-label={$t('common.download')}
                title={$t('common.download')}
                class="hidden md:flex bg-transparent border-none text-muma-spotify-text cursor-pointer p-1 items-center justify-center rounded hover:bg-muma-spotify-hover hover:text-white"
                onclick={(e) => e.stopPropagation()}
              >
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                      <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"></path>
                  </svg>
              </a>
          </div>
        </td>
      </tr>
    {/each}
  </tbody>
</table>
</div>

{#if detailsTrack}
  <LazyView name="trackDetails" fallback="none" props={{
    track: detailsTrack,
    rating: ratingOf(detailsTrack),
    onrate: (star) => updateRating(detailsTrack, star),
    onclose: () => (detailsTrack = null),
    onnavigate: detailsNavigate,
    durationLabel: durationCellText(detailsTrack),
    onlyrics: () => { showLyrics({ stopPropagation() {} }, detailsTrack); detailsTrack = null; },
    onplaynext: () => { addAfterCurrent({ stopPropagation() {} }, detailsTrack); detailsTrack = null; },
    onaddqueue: () => { addToEnd({ stopPropagation() {} }, detailsTrack); detailsTrack = null; },
    onremove: (isQueue || playlistId) ? () => { removeTrack({ stopPropagation() {} }, detailsIndex); detailsTrack = null; } : null,
    downloadsSupported,
    downloadState: downloadStateOf(detailsTrack),
    ondownload: () => { download({ stopPropagation() {} }, detailsTrack); detailsTrack = null; },
    onremovedownload: () => { removeDownload({ stopPropagation() {} }, detailsTrack); detailsTrack = null; },
  }} />
{/if}

{#if pendingSet}
  {@const size = trackSize(pendingSet)}
  <Modal title={$t('downloads.confirmTitle')} onclose={() => (pendingSet = null)}>
    <div class="flex flex-col gap-4 py-4" data-testid="set-size-confirm">
      <p class="text-white text-lg font-bold m-0">{pendingSet.title}</p>
      <!-- The size is the whole point of this sheet, so where it came from is
           part of it: `size` off the library when LMS sent one, otherwise
           bitrate times length, which the note underneath says out loud. -->
      <p class="text-2xl font-bold text-brand m-0" data-testid="set-size">{formatBytes(size.bytes, $locale)}</p>
      <p class="text-sm text-muma-spotify-text m-0">
        {size.estimated ? $t('downloads.sizeEstimated') : $t('downloads.sizeExact')}
      </p>
      <div class="flex gap-3 justify-end">
        <button
          class="bg-transparent border border-muma-spotify-muted text-white px-6 py-2 rounded-[24px] font-bold cursor-pointer hover:border-white"
          onclick={() => (pendingSet = null)}
        >{$t('common.cancel')}</button>
        <button
          class="bg-brand text-black px-6 py-2 rounded-[24px] font-bold cursor-pointer"
          onclick={() => start(pendingSet)}
        >{$t('downloads.download')}</button>
      </div>
    </div>
  </Modal>
{/if}

{#if selectedLyricsTrack}
  <Modal 
    title="Lyrics: {selectedLyricsTrack.title}" 
    onclose={() => selectedLyricsTrack = null}
  >
    <div class="flex flex-col items-center py-8">
      {#if isLoadingLyrics}
        <div class="flex items-center gap-2 text-muma-spotify-text">
          <svg class="animate-spin" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"></path>
          </svg>
          {$t('common.loading')}
        </div>
      {:else if lyricsLines.length > 0}
        <div class="max-w-2xl w-full text-center space-y-4">
          {#each lyricsLines as line, i (i)}
            <p class="text-xl md:text-3xl font-bold text-white hover:scale-105 transition-transform cursor-default">
              {line.value}
            </p>
          {/each}
        </div>
      {:else}
        <div class="text-muma-spotify-text text-center">
          <svg viewBox="0 0 24 24" width="48" height="48" fill="currentColor" class="mb-4 opacity-20 inline-block">
            <path d="M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z"></path>
          </svg>
          <p>{$t('track.noLyrics')}</p>
        </div>
      {/if}
    </div>
  </Modal>
{/if}
