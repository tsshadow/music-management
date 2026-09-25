<script>
  import { t } from './i18n/index.js';
  import { authParams, restUrl } from './store.js';
  import ArtistList from './ArtistList.svelte';
  import BottomSheet from './BottomSheet.svelte';
  import MetaChips from './MetaChips.svelte';
  import { coverArtSrc, localCoverArt } from './coverArt.js';
  import { offline } from './subsonic.js';
  import { releaseDateLabel, preferredReleaseDate, formatShortDate } from './trackDate.js';
  import { genreNames } from './genreSegments.js';
  import { fileName, folderOf, formatSummary, hasFileDetails, tagRows } from './trackFile.js';
  import { fetchTrackDetails } from './trackDetails.js';
  import { platform as defaultPlatform } from './platform/index.js';

  /**
   * Everything we know about one track, as a bottom sheet -- the web
   * equivalent of the old Kotlin app's `TrackInfoModalFragment`. Extracted out
   * of `TrackList.svelte`, which owned this markup inline before `NowPlaying`
   * needed the very same sheet for the track currently playing.
   *
   * Every navigable row (genre, label, festival, artist, album, "N versions")
   * reports through `onnavigate` with a router view string; the caller
   * decides what "navigate" means for it (`TrackList` just closes the sheet
   * first, `NowPlaying` also has to close the full-screen player first so the
   * sheet never ends up stranded over the destination screen).
   *
   * The queue-specific actions (lyrics, play next, add to queue, download,
   * remove) stay owned by whoever opened the sheet -- `TrackList` already has
   * the fetches and the optimistic state for them, and duplicating that here
   * would be a second copy to keep in sync. This component only renders the
   * button and calls back.
   *
   * @typedef {Object} Props
   * @property {Object} track
   * @property {number} [rating]
   * @property {function(number): void} [onrate]
   * @property {function(): void} onclose
   * @property {function(string): void} [onnavigate]
   * @property {string} [durationLabel] - Pre-formatted duration (the caller knows whether this is a song or a set).
   * @property {boolean} [hasLyrics] - Whether the lyrics row should render. Defaults to true so `TrackList`, which never checked, keeps showing it; `NowPlaying` (increment B) passes the real answer since it already fetched the lyrics.
   * @property {function(): void} [onlyrics]
   * @property {function(): void} [onplaynext]
   * @property {function(): void} [onaddqueue]
   * @property {function(): void} [onremove] - Removes the track from a queue/playlist; the button is hidden when null.
   * @property {boolean} [downloadsSupported]
   * @property {string} [downloadState] - One of none/queued/running/done/failed.
   * @property {function(): void} [ondownload]
   * @property {function(): void} [onremovedownload]
   * @property {Object} [platform] - The platform shim; the source URL goes through `system.openUrl` so the app hands it to the system browser instead of navigating the WebView away.
   */

  /** @type {Props} */
  let {
    track,
    rating = 0,
    onrate,
    onclose,
    onnavigate,
    durationLabel = '',
    hasLyrics = true,
    onlyrics,
    onplaynext,
    onaddqueue,
    onremove = null,
    downloadsSupported = false,
    downloadState = 'none',
    ondownload,
    onremovedownload,
    platform = defaultPlatform,
  } = $props();

  /** What joins two artists in "Headhunterz × Wildstylez samen" -- same glyph the Kotlin sheet used. */
  const TOGETHER_SEPARATOR = ' × ';

  const genres = $derived(genreNames(track?.genre));
  const labels = $derived.by(() => {
    if (Array.isArray(track?.labels) && track.labels.length) return track.labels.filter(Boolean);
    const single = track?.label || track?.publisher;
    return single ? [single] : [];
  });
  const moods = $derived.by(() => {
    if (Array.isArray(track?.moods)) return track.moods.filter(Boolean);
    return track?.mood ? [track.mood] : [];
  });
  /** `festivals` is what LMS sends (the FESTIVAL cluster, one array like `labels`); `festival` is the older single-value spelling the feeds hand out. */
  const festivals = $derived.by(() => {
    if (Array.isArray(track?.festivals) && track.festivals.length) return track.festivals.filter(Boolean);
    return track?.festival ? [track.festival] : [];
  });

  const artists = $derived.by(() => {
    if (track?.artists?.length) return track.artists;
    if (track?.artistId) return [{ id: track.artistId, name: track.artist }];
    return [];
  });
  const together = $derived(
    artists.length >= 2 ? artists.map((a) => a.name).join(TOGETHER_SEPARATOR) : null,
  );

  /** A bare year, the one thing the YEAR cluster on the server understands -- same rule the release date row used in Kotlin. */
  const releaseYear = $derived.by(() => {
    if (track?.year) return String(track.year);
    const preferred = preferredReleaseDate(track?.date, track?.originalDate);
    return preferred && /^\d{4}/.test(String(preferred)) ? String(preferred).slice(0, 4) : null;
  });

  const trackNumberLabel = $derived.by(() => {
    if (!track?.track) return null;
    return track?.discNumber
      ? `${track.track} · ${$t('track.disc', { number: track.discNumber })}`
      : String(track.track);
  });

  /**
   * The file section: name, format line, folder and the day it was added. All
   * of it is on the song object LMS sends, so it renders at once, no toggle --
   * the old "technical details" fold hid the file name behind two taps.
   */
  const fileSummary = $derived(
    formatSummary(track, {
      mono: $t('track.mono'),
      stereo: $t('track.stereo'),
      channels: (count) => $t('track.channels', { count }),
    }),
  );
  const addedOn = $derived(formatShortDate(track?.created));

  /**
   * The tags section is the one thing here MuMa has to be asked for, and it is
   * asked when the sheet opens rather than when the track starts: a listener
   * opens this for a fraction of the tracks they play. `none` (MuMa never
   * scanned the file) renders nothing; `error` says MuMa could not be reached,
   * because an empty section would read as "this file has no tags".
   */
  let tagState = $state('loading');
  let mumaDetails = $state(null);
  $effect(() => {
    const path = track?.path;
    let live = true;
    tagState = 'loading';
    mumaDetails = null;
    fetchTrackDetails(path).then((result) => {
      if (!live) return;
      mumaDetails = result.details;
      tagState = result.state;
    });
    return () => {
      live = false;
    };
  });
  const rows = $derived(tagRows(mumaDetails, track));

  function navigate(view) {
    onnavigate?.(view);
  }

  function openSource(event, url) {
    event.preventDefault();
    platform.system.openUrl(url).catch((error) => console.warn('Could not open the source', error));
  }
</script>

<BottomSheet title={$t('track.details')} {onclose}>
  <div class="p-4 flex flex-col gap-4" data-testid="song-details">
    <div class="flex gap-3 items-center">
      <img src={coverArtSrc(track.coverArt, 100, $authParams, $localCoverArt, $offline)} alt="" class="w-20 h-20 rounded object-cover" />
      <div class="min-w-0">
        <h3 class="text-base font-bold text-white">{track.title}</h3>
        <ArtistList artist={track.artist} artistId={track.artistId} artists={track.artists} onnavigate={navigate} />
        {#if track.albumId}
          <button
            class="block bg-transparent border-none p-0 text-sm text-[#b3b3b3] hover:text-white hover:underline cursor-pointer text-left"
            onclick={() => navigate(`album:${track.albumId}`)}
          >{track.album || ''}</button>
        {:else}
          <p class="text-sm text-[#b3b3b3] m-0">{track.album || ''}</p>
        {/if}
      </div>
    </div>

    {#if together}
      <button
        class="self-start px-3 py-1.5 rounded-full text-[13px] font-bold bg-[#282828] text-[#b3b3b3] hover:text-white hover:bg-[#333] border-none cursor-pointer"
        data-testid="artist-together"
        onclick={() => navigate(`search:${together}`)}
      >{$t('track.artistsTogether', { names: together })}</button>
    {/if}

    {#if genres.length}
      <div class="flex flex-col gap-1">
        <span class="text-[10px] font-bold uppercase tracking-[0.1em] text-[#727272]">{$t('nav.genres')}</span>
        <MetaChips
          items={genres.map((genre) => ({ text: genre, view: `genre:${genre}`, testid: 'genre-chip', kind: 'genre' }))}
          onnavigate={navigate}
        />
      </div>
    {/if}

    {#if labels.length}
      <div class="flex flex-col gap-1">
        <span class="text-[10px] font-bold uppercase tracking-[0.1em] text-[#727272]">{$t('nav.labels')}</span>
        <MetaChips
          items={labels.map((label) => ({ text: label, view: `label:${label}`, testid: 'label-chip', kind: 'label' }))}
          onnavigate={navigate}
        />
      </div>
    {/if}

    {#if festivals.length}
      <div class="flex flex-col gap-1">
        <span class="text-[10px] font-bold uppercase tracking-[0.1em] text-[#727272]">{$t('nav.festivals')}</span>
        <MetaChips
          items={festivals.map((festival) => ({ text: festival, view: `festival:${festival}`, testid: 'festival-chip', kind: 'festival' }))}
          onnavigate={navigate}
        />
      </div>
    {/if}

    {#if moods.length}
      <div class="flex flex-col gap-1">
        <span class="text-[10px] font-bold uppercase tracking-[0.1em] text-[#727272]">{$t('track.moods')}</span>
        <div class="flex flex-wrap gap-1.5">
          {#each moods as mood (mood)}
            <span class="px-3 py-1.5 rounded-full text-[13px] font-bold bg-[#282828] text-[#b3b3b3]" data-testid="mood-chip">{mood}</span>
          {/each}
        </div>
      </div>
    {/if}

    <div class="text-xs text-[#b3b3b3] flex flex-col gap-1">
      {#if trackNumberLabel}<span>{trackNumberLabel}</span>{/if}
      {#if releaseDateLabel(track)}
        <button
          class="self-start bg-transparent border-none p-0 text-inherit hover:text-white hover:underline cursor-pointer {releaseYear ? '' : 'pointer-events-none'}"
          onclick={() => releaseYear && navigate(`year:${releaseYear}`)}
        >{$t('track.releaseDate')}: {releaseDateLabel(track)}</button>
      {/if}
      <span>{durationLabel} • {$t('track.plays')}: {track.globalPlayCount ?? track.playCount ?? 0}</span>
    </div>

    {#if hasFileDetails(track)}
      <div class="flex flex-col gap-1" data-testid="file-details">
        <span class="text-[10px] font-bold uppercase tracking-[0.1em] text-[#727272]">{$t('track.file')}</span>
        <dl class="details-list m-0 text-xs">
          {#if track.path}
            <dt>{$t('track.fileName')}</dt><dd class="break-all text-white" data-testid="file-name">{fileName(track.path)}</dd>
          {/if}
          {#if fileSummary}
            <dt>{$t('track.format')}</dt><dd data-testid="file-format">{fileSummary}</dd>
          {/if}
          {#if folderOf(track.path)}
            <dt>{$t('track.folder')}</dt><dd class="break-all">{folderOf(track.path)}</dd>
          {/if}
          {#if addedOn}
            <dt>{$t('track.added')}</dt><dd>{addedOn}</dd>
          {/if}
        </dl>
      </div>
    {/if}

    {#if tagState === 'loading' || tagState === 'error' || rows.length}
      <div class="flex flex-col gap-1" data-testid="tag-details">
        <span class="text-[10px] font-bold uppercase tracking-[0.1em] text-[#727272]">{$t('track.tags')}</span>
        {#if tagState === 'loading'}
          <span class="text-xs text-[#727272]">{$t('track.tagsLoading')}</span>
        {:else if tagState === 'error'}
          <span class="text-xs text-[#727272]" data-testid="tags-unavailable">{$t('track.tagsUnavailable')}</span>
        {:else}
          <dl class="details-list m-0 text-xs">
            {#each rows as row (row.key + row.value)}
              <dt>{row.raw ? row.key : $t(`track.${row.key}`)}</dt>
              <dd class="break-all">
                {#if row.href}
                  <a href={row.href} target="_blank" rel="noopener noreferrer" class="text-brand hover:underline" onclick={(e) => openSource(e, row.href)}>{row.value}</a>
                {:else if row.view}
                  <button class="bg-transparent border-none p-0 text-inherit text-left hover:text-white hover:underline cursor-pointer" data-testid="tag-link" onclick={() => navigate(row.view)}>{row.value}</button>
                {:else}
                  {row.value}
                {/if}
              </dd>
            {/each}
          </dl>
        {/if}
      </div>
    {/if}

    <div class="flex gap-1">
      {#each [1, 2, 3, 4, 5] as star (star)}
        <button class="w-10 h-10 border-none bg-transparent text-xl cursor-pointer {rating >= star ? 'text-brand' : 'text-[#b3b3b3]'}" aria-label={$t('car.rate', { star })} onclick={(e) => { e.stopPropagation(); onrate?.(star); }}>★</button>
      {/each}
    </div>

    <div class="details-actions flex flex-col">
      {#if track.workId}<button onclick={() => navigate(`song:${track.workId}`)}>{$t('track.versions')}</button>{/if}
      {#if hasLyrics}<button onclick={() => onlyrics?.()}>{$t('track.lyrics')}</button>{/if}
      <button onclick={() => onplaynext?.()}>{$t('track.playNext')}</button>
      <button onclick={() => onaddqueue?.()}>{$t('track.addToQueue')}</button>
      {#if downloadsSupported}
        {#if ['none', 'failed'].includes(downloadState)}
          <button onclick={() => ondownload?.()}>{$t('downloads.download')}</button>
        {:else}
          <button onclick={() => onremovedownload?.()}>{$t('downloads.remove')}</button>
        {/if}
      {/if}
      <a href={restUrl(`/rest/download?id=${track.id}&${$authParams}`)} download={`${track.artist} - ${track.title}.mp3`} onclick={(e) => e.stopPropagation()}>{$t('track.browserDownload')}</a>
      {#if track.albumId}<button onclick={() => navigate(`album:${track.albumId}`)}>{$t('track.goToAlbum')}</button>{/if}
      {#each artists as artist (artist.id)}
        <button onclick={() => navigate(`artist:${artist.id}`)}>{$t('track.goToArtist')}: {artist.name}</button>
      {/each}
      {#if onremove}
        <button onclick={() => onremove?.()}>{$t('common.remove')}</button>
      {/if}
    </div>
  </div>
</BottomSheet>

<style>
  /* Label left, value right, wrapping under each other on a narrow sheet. */
  .details-list {
    display: grid;
    grid-template-columns: max-content 1fr;
    column-gap: .75rem;
    row-gap: .25rem;
    color: #b3b3b3;
  }
  .details-list dt {
    color: #727272;
  }
  .details-list dd {
    margin: 0;
    min-width: 0;
  }

  /* One shared touch target for every details action, including the download link. */
  .details-actions > button, .details-actions > a {
    min-height: 44px;
    padding: .75rem 0;
    text-align: left;
    background: transparent;
    border: 0;
    color: white;
    font-size: .875rem;
    cursor: pointer;
  }
</style>
