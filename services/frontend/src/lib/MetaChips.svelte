<script>
  /**
   * The pill-shaped chip row shared by `NowPlaying`'s genre/label line and
   * `TrackDetailsSheet`'s genre and label groups. Both screens rendered the
   * same button-or-span markup inline before increment B; this is that
   * markup pulled out once so a future style change (or a third caller)
   * touches one file instead of two kept in sync by hand.
   *
   * @typedef {Object} ChipItem
   * @property {string} text - What the chip reads.
   * @property {string|null} [view] - A router view string (`genre:x`, `label:y`, ...); a falsy value renders a plain, non-navigable span with the same look.
   * @property {string} [testid] - `data-testid` for this one chip, for tests that need to tell it apart from its siblings.
   *
   * @typedef {Object} Props
   * @property {ChipItem[]} [items]
   * @property {function(string): void} [onnavigate] - Called with `item.view` when a navigable chip is tapped.
   * @property {string} [testid] - `data-testid` for the wrapping row.
   * @property {boolean} [wrap] - `true` (default) wraps onto as many rows as the chips need;
   *   `false` keeps them on one row that scrolls sideways, for a screen where every extra row
   *   pushes something more important out of view (the Now Playing controls).
   */

  /** @type {Props} */
  let { items = [], onnavigate, testid = undefined, wrap = true } = $props();

  /** Shared look for every chip, navigable or not. */
  const CHIP_CLASS =
    'px-3 py-1.5 rounded-full text-[13px] font-bold bg-[#282828] text-[#b3b3b3] hover:text-white hover:bg-[#333] border-none cursor-pointer';
</script>

<div
  class="flex gap-2 {wrap ? 'flex-wrap' : 'flex-nowrap overflow-x-auto overscroll-x-contain scrollbar-hide'}"
  data-testid={testid}
  data-wrap={wrap}
>
  {#each items as item, i (item.text + i)}
    {#if item.view}
      <button
        class="{CHIP_CLASS} {wrap ? '' : 'shrink-0 whitespace-nowrap'}"
        data-testid={item.testid}
        onclick={() => onnavigate?.(item.view)}
      >{item.text}</button>
    {:else}
      <span class="{CHIP_CLASS} {wrap ? '' : 'shrink-0 whitespace-nowrap'}" data-testid={item.testid}>{item.text}</span>
    {/if}
  {/each}
</div>
