<script>
  /** One fact: a headline and the sentence that explains it. An artist fact links to the artist. */
  import CardFrame from './CardFrame.svelte';

  const { face, tint = null, onshare = null, onlink = null } = $props();
</script>

<CardFrame {face} {tint} {onshare}>
  {#if face.link && onlink}
    <button
      type="button"
      class="self-start bg-transparent border border-white/40 rounded-full px-4 py-1.5 text-sm font-bold text-white cursor-pointer hover:border-white"
      onclick={() => onlink(face.link)}
    >{face.link.name}</button>
  {/if}
</CardFrame>
