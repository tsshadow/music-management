<script>
  import { t } from './i18n/index.js';
  import { authParams, restUrl } from './store.js';
  import ArtistList from './ArtistList.svelte';
  import BottomSheet from './BottomSheet.svelte';
  import { coverArtSrc, localCoverArt } from './coverArt.js';
  import { offline } from './subsonic.js';
  import { releaseDateLabel, preferredReleaseDate } from './trackDate.js';
  import { genreNames } from './genreSegments.js';

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
   * @property {function(): void} [onlyrics]
   * @property {function(): void} [onplaynext]
   * @property {function(): void} [onaddqueue]
   * @property {function(): void} [onremove] - Removes the track from a queue/playlist; the button is hidden when null.
   * @property {boolean} [downloadsSupported]
   * @property {string} [downloadState] - One of none/queued/running/done/failed.
   * @property {function(): void} [ondownload]
   * @property {function(): void} [onremovedownload]
   */

  /** @type {Props} */
  let {
    track,
    rating = 0,
    onrate,
    onclose,
    onnavigate,
    durationLabel = '',
    onlyrics,
    onplaynext,
    onaddqueue,
    onremove = null,
    downloadsSupported = false,
    downloadState = 'none',
    ondownload,
    onremovedownload,
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
  const festival = $derived(track?.festival || null);

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

  const technicalSummary = $derived.by(() => {
    const parts = [];
    if (track?.bitRate > 0) parts.push(`${track.bitRate} kbps`);
    if (track?.suffix) parts.push(String(track.suffix).toUpperCase());
    return parts.join(' · ');
  });
  const hasTechnicalDetails = $derived(technicalSummary !== '' || !!track?.path);

  let showTechnical = $state(false);

  function navigate(view) {
    onnavigate?.(view);
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
        <div class="flex flex-wrap gap-1.5">
          {#each genres as genre (genre)}
            <button
              class="px-3 py-1.5 rounded-full text-[13px] font-bold bg-[#282828] text-[#b3b3b3] hover:text-white hover:bg-[#333] border-none cursor-pointer"
              data-testid="genre-chip"
              onclick={() => navigate(`genre:${genre}`)}
            >{genre}</button>
          {/each}
        </div>
      </div>
    {/if}

    {#if labels.length}
      <div class="flex flex-col gap-1">
        <span class="text-[10px] font-bold uppercase tracking-[0.1em] text-[#727272]">{$t('nav.labels')}</span>
        <div class="flex flex-wrap gap-1.5">
          {#each labels as label (label)}
            <button
              class="px-3 py-1.5 rounded-full text-[13px] font-bold bg-[#282828] text-[#b3b3b3] hover:text-white hover:bg-[#333] border-none cursor-pointer"
              data-testid="label-chip"
              onclick={() => navigate(`label:${label}`)}
            >{label}</button>
          {/each}
        </div>
      </div>
    {/if}

    {#if festival}
      <div class="flex flex-col gap-1">
        <span class="text-[10px] font-bold uppercase tracking-[0.1em] text-[#727272]">{$t('nav.festivals')}</span>
        <button
          class="self-start px-3 py-1.5 rounded-full text-[13px] font-bold bg-[#282828] text-[#b3b3b3] hover:text-white hover:bg-[#333] border-none cursor-pointer"
          data-testid="festival-chip"
          onclick={() => navigate(`festival:${festival}`)}
        >{festival}</button>
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

    {#if hasTechnicalDetails}
      <div>
        <button
          class="flex items-center gap-1 bg-transparent border-none p-0 text-[#b3b3b3] hover:text-white cursor-pointer text-xs font-bold uppercase tracking-[0.1em]"
          data-testid="technical-toggle"
          aria-expanded={showTechnical}
          onclick={() => (showTechnical = !showTechnical)}
        >
          {$t('track.technical')}
          <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor" class="transition-transform {showTechnical ? 'rotate-180' : ''}">
            <path d="M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z"></path>
          </svg>
        </button>
        {#if showTechnical}
          <div class="mt-2 flex flex-col gap-1 text-xs text-[#b3b3b3]" data-testid="technical-body">
            {#if technicalSummary}<span>{$t('track.format')}: {technicalSummary}</span>{/if}
            {#if track.path}<span class="break-all">{$t('track.path')}: {track.path}</span>{/if}
          </div>
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
      <button onclick={() => onlyrics?.()}>{$t('track.lyrics')}</button>
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
