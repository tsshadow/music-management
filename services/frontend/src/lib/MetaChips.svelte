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
   * @property {'genre'|'label'|'festival'} [kind] - What the chip names. Colours the chip by kind
   *   (styleguide increment L): a label is amber, everything else the neutral grey. Leave it out
   *   for the neutral look.
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

  /** Shared shape for every chip, navigable or not; the colours come from `chipColour`. */
  const CHIP_CLASS = 'px-3 py-1.5 rounded-full text-[13px] font-bold border-none cursor-pointer';

  /**
   * Colours per chip kind (docs/styleguide.md, increment L). Written out in full so
   * Tailwind's scanner sees every class; a kind not listed here gets `NEUTRAL`.
   */
  const NEUTRAL = 'bg-muma-spotify-light text-muma-spotify-text hover:text-white hover:bg-muma-spotify-hover';
  const KIND_CLASS = {
    label: 'bg-[#3a2c16] text-[#ffcc80] hover:text-[#ffe0b2] hover:bg-[#4a3820]',
  };

  /**
   * The colour classes for one chip, by what it names rather than where it sits.
   * @param {ChipItem} item
   * @returns {string}
   */
  function chipColour(item) {
    return (item.kind && KIND_CLASS[item.kind]) || NEUTRAL;
  }
</script>

<div
  class="flex gap-2 {wrap ? 'flex-wrap' : 'flex-nowrap overflow-x-auto overscroll-x-contain scrollbar-hide'}"
  data-testid={testid}
  data-wrap={wrap}
>
  {#each items as item, i (item.text + i)}
    {#if item.view}
      <button
        class="{CHIP_CLASS} {chipColour(item)} {wrap ? '' : 'shrink-0 whitespace-nowrap'}"
        data-testid={item.testid}
        data-kind={item.kind}
        onclick={() => onnavigate?.(item.view)}
      >{item.text}</button>
    {:else}
      <span
        class="{CHIP_CLASS} {chipColour(item)} {wrap ? '' : 'shrink-0 whitespace-nowrap'}"
        data-testid={item.testid}
        data-kind={item.kind}
      >{item.text}</span>
    {/if}
  {/each}
</div>
