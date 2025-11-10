<script lang="ts">
  export interface HypePoint {
    label: string;
    value: number;
  }

  export let points: HypePoint[] = [];

  const viewHeight = 100;

  $: sanitized = points.filter((point) => Number.isFinite(point.value) && point.value >= 0);
  $: maxValue = sanitized.reduce((max, point) => Math.max(max, point.value), 0);
  $: normalizedMax = maxValue > 0 ? maxValue : 1;
  $: count = sanitized.length;
  $: coordinates = sanitized.map((point, index) => {
    const x = count === 1 ? 50 : (index / (count - 1)) * 100;
    const y = viewHeight - (point.value / normalizedMax) * (viewHeight - 10);
    return { x, y };
  });
  $: polylinePoints = coordinates.map(({ x, y }) => `${x},${y}`).join(' ');
  $: areaPath = count
    ? `M 0 ${viewHeight} ` +
      coordinates
        .map(({ x, y }) => `L ${x} ${Number.isFinite(y) ? y : viewHeight}`)
        .join(' ') +
      ` L 100 ${viewHeight} Z`
    : '';
</script>

<div class="graph" role="img" aria-label="Luistergeschiedenis voor geselecteerde artiest">
  {#if count === 0}
    <p class="empty">Nog geen luisterdata</p>
  {:else}
    <svg viewBox={`0 0 100 ${viewHeight}`} preserveAspectRatio="none">
      <defs>
        <linearGradient id="hypeGradient" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stop-color="rgba(255, 140, 0, 0.7)" />
          <stop offset="100%" stop-color="rgba(255, 140, 0, 0.05)" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill="url(#hypeGradient)" />
      <polyline points={polylinePoints} fill="none" stroke="rgb(255, 180, 80)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
      {#each coordinates as point, index}
        <circle cx={point.x} cy={point.y} r="2.2" fill="rgb(255, 220, 160)">
          <title>{sanitized[index].label}: {sanitized[index].value.toLocaleString()} listens</title>
        </circle>
      {/each}
    </svg>
    <ul class="labels">
      {#each sanitized as point, index}
        <li>
          <span class="label">{point.label}</span>
          <span class="value">{point.value.toLocaleString()}</span>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .graph {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  svg {
    width: 100%;
    height: 180px;
    background: rgba(255, 255, 255, 0.05);
    border-radius: 0.75rem;
    padding: 0.75rem;
  }

  .labels {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
    gap: 0.5rem;
    list-style: none;
    padding: 0;
    margin: 0;
    font-size: 0.85rem;
    color: rgba(255, 255, 255, 0.7);
  }

  .labels .label {
    display: block;
    font-weight: 600;
    color: rgba(255, 255, 255, 0.85);
  }

  .labels .value {
    font-variant-numeric: tabular-nums;
  }

  .empty {
    text-align: center;
    color: rgba(255, 255, 255, 0.6);
    margin: 0;
  }
</style>
