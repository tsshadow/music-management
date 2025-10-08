<script lang="ts">
  import { onMount } from 'svelte';
  import StatsLeaderboard, { type LeaderboardRow } from '../lib/components/StatsLeaderboard.svelte';

  type Period = 'day' | 'month' | 'year';

  let period: Period = 'year';
  let value = getDefaultValue(period);
  let loading = false;
  let error: string | null = null;
  let rows: LeaderboardRow[] = [];

  function getDefaultValue(current: Period): string {
    const now = new Date();
    if (current === 'day') {
      return now.toISOString().slice(0, 10);
    }
    if (current === 'month') {
      const month = String(now.getMonth() + 1).padStart(2, '0');
      return `${now.getFullYear()}-${month}`;
    }
    return String(now.getFullYear());
  }

  async function loadData() {
    if (!value) {
      rows = [];
      return;
    }
    loading = true;
    error = null;
    try {
      const params = new URLSearchParams({ period, value });
      const response = await fetch(`/api/v1/stats/genres?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Kon de genres niet laden');
      }
      const data: { genre: string; count: number }[] = await response.json();
      rows = data.map((item) => ({ label: item.genre, count: item.count }));
    } catch (err) {
      error = err instanceof Error ? err.message : 'Onbekende fout';
      rows = [];
    } finally {
      loading = false;
    }
  }

  function onPeriodChange(event: Event) {
    period = (event.target as HTMLSelectElement).value as Period;
    value = getDefaultValue(period);
    loadData();
  }

  function onValueChange(event: Event) {
    value = (event.target as HTMLInputElement).value;
    loadData();
  }

  onMount(() => {
    loadData();
  });
</script>

<section class="page">
  <header>
    <h2>Meest geluisterde genres</h2>
    <p>Kies een periode om te zien welke genres je het meest draaide.</p>
  </header>

  <div class="controls">
    <label>
      Periode
      <select bind:value={period} on:change={onPeriodChange}>
        <option value="day">Dag</option>
        <option value="month">Maand</option>
        <option value="year">Jaar</option>
      </select>
    </label>

    <label>
      Waarde
      {#if period === 'year'}
        <input
          type="text"
          inputmode="numeric"
          maxlength="4"
          bind:value={value}
          on:change={onValueChange}
        />
      {:else if period === 'month'}
        <input type="month" bind:value={value} on:change={onValueChange} />
      {:else}
        <input type="date" bind:value={value} on:change={onValueChange} />
      {/if}
    </label>
  </div>

  {#if loading}
    <p class="status">Bezig met laden…</p>
  {:else if error}
    <p class="status error">{error}</p>
  {:else}
    <div class="table-wrapper">
      <StatsLeaderboard {rows} labelHeading="Genre" />
    </div>
  {/if}
</section>

<style>
  .page {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    padding: 0 2rem 4rem;
    align-items: center;
  }

  header {
    text-align: center;
  }

  .controls {
    display: flex;
    gap: 1rem;
    background: rgba(0, 0, 0, 0.15);
    padding: 1rem 1.5rem;
    border-radius: 999px;
    flex-wrap: wrap;
    justify-content: center;
  }

  label {
    display: flex;
    flex-direction: column;
    font-size: 0.9rem;
    gap: 0.35rem;
    color: rgba(255, 255, 255, 0.75);
  }

  select,
  input {
    padding: 0.5rem 0.75rem;
    border-radius: 0.75rem;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(20, 20, 30, 0.8);
    color: var(--text-color);
  }

  .table-wrapper {
    width: min(720px, 100%);
    background: rgba(0, 0, 0, 0.15);
    border-radius: 1rem;
    padding: 1rem;
  }

  .status {
    color: rgba(255, 255, 255, 0.75);
  }

  .status.error {
    color: #ff8080;
  }
</style>
