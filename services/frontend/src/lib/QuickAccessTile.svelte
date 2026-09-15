<script>
  /** A compact home destination: artwork/colour, title and one line of context. */
  const { title, subtitle = '', cover = null, color = '#503750', onclick } = $props();
</script>

<button type="button" class="min-w-0 flex items-center gap-2 overflow-hidden rounded bg-[#282828] hover:bg-[#333] text-left border-none p-0 cursor-pointer" {onclick}>
  {#if cover}
    <img src={cover} alt="" class="w-12 h-12 shrink-0 object-cover" />
  {:else}
    <span class="w-12 h-12 shrink-0 flex items-center justify-center text-white text-xl" style:background-color={color} aria-hidden="true">♪</span>
  {/if}
  <span class="min-w-0 pr-2 py-1">
    <span class="block text-white text-sm font-bold truncate">{title}</span>
    <span class="block text-[#b3b3b3] text-xs truncate">{subtitle}</span>
  </span>
</button>
