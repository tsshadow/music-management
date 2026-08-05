<script>
  /**
   * The MuMa mark: five bars whose top edge traces an M.
   *
   * Draws in `currentColor`, so the caller decides the colour. The canonical
   * full-colour artwork lives in `docs/branding/`; this is the in-app version.
   */
  const { size = 20, title = 'MuMa' } = $props();

  const bars = [
    { x: 3, top: 5 },
    { x: 7.5, top: 8.5 },
    { x: 12, top: 11.5 },
    { x: 16.5, top: 8.5 },
    { x: 21, top: 5 },
  ];
</script>

<svg
  viewBox="0 0 24 24"
  width={size}
  height={size}
  fill="none"
  stroke="currentColor"
  stroke-width="2.6"
  stroke-linecap="round"
  role="img"
  aria-label={title}
>
  {#each bars as bar (bar.x)}
    <path d="M{bar.x} {bar.top} V19" />
  {/each}
</svg>
