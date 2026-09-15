<script>
  /**
   * A compact home/preset destination tile: the Browse grid's tile look
   * (`BrowseGrid.svelte`, solid colour, bold title, rotated icon watermark) at roughly
   * two thirds the height, with a one-line subtitle underneath the title -- the same
   * layout the preset tiles used before they moved to `QuickAccessTile` (see
   * `PresetGrid.svelte`'s desktop branch, still on develop).
   *
   * `cover`, when given, replaces the colour+icon with a full-bleed photo: the tile that
   * points at real tracks (Home's shelves, a memory) can show their artwork, while
   * category tiles (Browse, presets) keep the flat colour and icon instead.
   */
  const {
    title,
    subtitle = '',
    cover = null,
    color = '#503750',
    icon = 'M12 3v10.55A4 4 0 1 0 14 17V7h4V3h-6z',
    onclick,
  } = $props();
</script>

<button
  type="button"
  class="relative overflow-hidden rounded-lg h-16 p-2.5 border-none cursor-pointer text-left flex flex-col justify-between hover:brightness-110 active:scale-[0.98] transition"
  style={cover
    ? `background-image: url("${cover}"); background-size: cover; background-position: center;`
    : `background-color: ${color};`}
  {onclick}
>
  <!-- A cover photo's brightness is unknown; a colour tint can be as bright as the brand
       green. Either way the wash keeps white text readable. -->
  <span class="absolute inset-0 {cover ? 'bg-black/45' : 'bg-black/25'}" aria-hidden="true"></span>
  <span class="relative z-10 text-white font-bold text-sm leading-tight line-clamp-1">{title}</span>
  <span class="relative z-10 text-white/70 text-[11px] truncate">{subtitle}</span>
  {#if !cover}
    <svg
      viewBox="0 0 24 24"
      width="40"
      height="40"
      fill="white"
      class="absolute -right-2 -bottom-2 rotate-12 opacity-40"
      aria-hidden="true"
    >
      <path d={icon}></path>
    </svg>
  {/if}
</button>
