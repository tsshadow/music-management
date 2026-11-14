<script>
  /**
   * The frame every Wrapped card shares: the tinted panel, the card's label, its headline and
   * sentence, the notes on what it was based on, and the round share button in the top right
   * corner (docs/styleguide.md, "Wrapped card"). The card kinds fill the space between the
   * sentence and the notes through `children`.
   */
  import { Share2 } from '@lucide/svelte';
  import { t } from '../i18n/index.js';

  const {
    face,
    tint = null,
    hero = false,
    onshare = null,
    children = undefined,
  } = $props();

  const background = $derived(
    tint ? `background: linear-gradient(160deg, ${tint}, #121212 70%);` : '',
  );
</script>

<article
  class="relative flex flex-col gap-4 rounded-lg p-6 md:p-8 min-h-[100dvh] md:min-h-0 snap-start overflow-hidden {tint ? '' : 'bg-muma-spotify-panel'} {hero ? 'md:col-span-2' : ''}"
  style={background}
  data-testid="wrapped-card"
  data-card={face.id}
  data-kind={face.kind}
>
  {#if onshare}
    <button
      type="button"
      class="absolute top-4 right-4 w-10 h-10 rounded-full bg-black/40 hover:bg-black/60 border-none cursor-pointer flex items-center justify-center text-white"
      aria-label={$t('wrapped.share')}
      title={$t('wrapped.share')}
      onclick={() => onshare(face)}
    >
      <Share2 size={18} />
    </button>
  {/if}
  <p class="m-0 pr-12 text-sm font-bold uppercase tracking-[0.1em] text-white/80">{face.label}</p>
  {#if face.headline}
    <h2 class="m-0 font-black text-5xl {hero ? 'md:text-7xl' : ''} leading-tight break-words">{face.headline}</h2>
  {/if}
  {#if face.sentence}
    <p class="m-0 text-lg text-white/90">{face.sentence}</p>
  {/if}
  {@render children?.()}
  {#if face.notes.length > 0}
    <ul class="m-0 mt-auto p-0 list-none flex flex-col gap-1 text-xs text-white/60" data-testid="wrapped-notes">
      {#each face.notes as note, index (index)}
        <li>{note}</li>
      {/each}
    </ul>
  {/if}
</article>
