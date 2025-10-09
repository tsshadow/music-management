<script lang="ts">
  import { onMount } from 'svelte';
  import StatsLeaderboard, { type LeaderboardRow } from '../lib/components/StatsLeaderboard.svelte';

  type Period = 'all' | 'day' | 'month' | 'year';

  let period: Period = 'year';
  let value = getDefaultValue(period);
  let loading = false;
  let error: string | null = null;
  let rows: LeaderboardRow[] = [];

  function getDefaultValue(current: Period): string {
    const now = new Date();
    if (current === 'all') {
      return '';
    }
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
    if (period !== 'all' && !value) {
      rows = [];
      return;
    }
    loading = true;
    error = null;
    try {
      const params = new URLSearchParams({ period });
      if (period !== 'all') {
        params.set('value', value);
      }
      const response = await fetch(`/api/v1/stats/albums?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Kon de albums niet laden');
      }
      const data: { album: string; count: number }[] = await response.json();
      rows = data.map((item) => ({ label: item.album, count: item.count }));
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
    <h2>Meest geluisterde albums</h2>
    <p>Bekijk welke releases je keer op keer hebt gedraaid.</p>
  </header>

  <div class="controls">
    <label>
      Periode
      <select bind:value={period} on:change={onPeriodChange}>
        <option value="all">Altijd</option>
        <option value="day">Dag</option>
        <option value="month">Maand</option>
        <option value="year">Jaar</option>
      </select>
    </label>

    <label class:disabled={period === 'all'}>
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
      {:else if period === 'day'}
        <input type="date" bind:value={value} on:change={onValueChange} />
      {:else}
        <span class="all-time-pill">Alles</span>
      {/if}
    </label>
  </div>

  {#if loading}
    <p class="status">Bezig met laden…</p>
  {:else if error}
    <p class="status error">{error}</p>
  {:else}
    <div class="table-wrapper">
      <StatsLeaderboard {rows} labelHeading="Album" />
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

  label.disabled {
    opacity: 0.6;
  }

  select,
  input {
    padding: 0.5rem 0.75rem;
    border-radius: 0.75rem;
    border: 1px solid rgba(255, 255, 255, 0.2);
    background: rgba(20, 20, 30, 0.8);
    color: var(--text-color);
  }

  .all-time-pill {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    padding: 0.5rem 0.75rem;
    background: rgba(255, 255, 255, 0.08);
    border-radius: 999px;
    font-weight: 600;
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
