<script>
  /**
   * A minimal host for testing `BottomSheet.svelte` in isolation: the sheet
   * itself has no content of its own, so a real `.svelte` file is what lets a
   * test render actual option buttons into its `children` snippet -- a plain
   * JS function cannot stand in for a Svelte snippet.
   */
  import BottomSheet from '../../../src/lib/BottomSheet.svelte';

  let { onclose, title = 'Title', selected = null, options = ['One', 'Two'], onselect } = $props();
</script>

<BottomSheet {title} {onclose}>
  {#each options as option (option)}
    <button
      type="button"
      onclick={() => onselect?.(option)}
      aria-pressed={selected === option}
    >{option}</button>
  {/each}
</BottomSheet>
