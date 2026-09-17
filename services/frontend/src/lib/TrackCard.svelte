<script>
  import { t } from './i18n/index.js';
  import { authParams, isMobile } from './store.js';
  import { offline } from './subsonic.js';
  import { coverArtSrc, FALLBACK, localCoverArt } from './coverArt.js';
  import { playTrack } from './playTrack.js';
  import ArtistList from './ArtistList.svelte';
  import Artwork from './Artwork.svelte';

  const { track, onnavigate } = $props();

  // `coverArtSrc` is the one place that knows whether this device has a local, offline copy of
  // the art -- the same helper the player uses -- so this card no longer builds
  // `/rest/getCoverArt` URLs by hand and agrees with every other list about what "offline"
  // shows. It answers a missing cover with `FALLBACK` (the MuMa mark svg); `Artwork` wants
  // `null` for "no cover" instead, so it can fall through to its own tinted panel rather than
  // rendering that mark as if it were the cover.
  const coverUrl = $derived.by(() => {
    const src = coverArtSrc(track.coverArt, 300, $authParams, $localCoverArt, $offline);
    return src === FALLBACK ? null : src;
  });
</script>

<div
  role="button"
  tabindex="0"
  class="bg-[#181818] rounded-lg transition-colors cursor-pointer flex flex-col group hover:bg-[#282828] {$isMobile ? 'p-2 gap-1.5' : 'p-4 gap-3'}"
  onclick={() => playTrack(track)}
  onkeydown={(e) => e.key === 'Enter' && playTrack(track)}
>
  <div class="relative aspect-square shadow-[0_8px_24px_rgba(0,0,0,0.5)] rounded overflow-hidden">
    <!-- No artist image here: a card is a track, not an artist, and the panel fallback (title on
         a tinted background) already reads better than a stranger's face would. -->
    <Artwork class="w-full h-full" {coverUrl} artistUrl={null} title={track.title || track.name} alt={track.title} />
    <button
      aria-label={$t('common.play')}
      class="absolute right-2 bottom-2 w-12 h-12 bg-brand border-none rounded-full flex items-center justify-center shadow-[0_8px_16px_rgba(0,0,0,0.3)] opacity-0 translate-y-2 transition-all group-hover:opacity-100 group-hover:translate-y-0"
      onclick={(e) => { e.stopPropagation(); playTrack(track); }}
    >
      <svg viewBox="0 0 24 24" width="24" height="24" fill="black">
        <path d="M7 6v12l10-6z"></path>
      </svg>
    </button>
  </div>
  <div class="flex flex-col min-w-0">
    <span class="text-base font-bold whitespace-nowrap overflow-hidden text-ellipsis">{track.title || track.name}</span>
    <div class="truncate">
      <ArtistList artist={track.artist} artistId={track.artistId} artists={track.artists} onnavigate={onnavigate} />
    </div>
  </div>
</div>

<style>
</style>
