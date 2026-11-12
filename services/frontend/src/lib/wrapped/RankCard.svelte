<script>
  /**
   * A ranked list: top tracks, artists, genres, labels and the like. An entry with a link opens
   * its page; a card of tracks gets a play button that queues them all.
   */
  import { Play } from '@lucide/svelte';
  import { t } from '../i18n/index.js';
  import CardFrame from './CardFrame.svelte';

  const { face, tint = null, onshare = null, onlink = null, onplay = null } = $props();
</script>

<CardFrame {face} {tint} {onshare}>
  <ol class="m-0 p-0 list-none flex flex-col gap-2">
    {#each face.items ?? [] as item, index (index)}
      <li class="flex items-center gap-3 min-w-0">
        <span class="w-6 shrink-0 text-right font-bold text-white/60">{index + 1}</span>
        <span class="flex-1 min-w-0">
          {#if item.link && onlink}
            <button
              type="button"
              class="block max-w-full truncate bg-transparent border-none p-0 text-left text-white font-bold cursor-pointer hover:underline"
              onclick={() => onlink(item.link)}
            >{item.label}</button>
          {:else}
            <span class="block truncate font-bold">{item.label}</span>
          {/if}
          {#if item.sub}
            <span class="block truncate text-sm text-white/70">{item.sub}</span>
          {/if}
        </span>
        <span class="shrink-0 text-sm text-white/70">{item.value}</span>
      </li>
    {/each}
  </ol>
  {#if face.playable && onplay}
    <button
      type="button"
      class="self-start flex items-center gap-2 rounded-full bg-brand text-black font-bold px-5 py-2 border-none cursor-pointer hover:scale-105 transition"
      onclick={() => onplay(face)}
    >
      <Play size={16} fill="currentColor" />
      {$t('wrapped.play')}
    </button>
  {/if}
</CardFrame>
