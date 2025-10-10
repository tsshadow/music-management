<script lang="ts">
  import { onMount } from 'svelte';
  import StatsLeaderboard, { type LeaderboardRow } from '../lib/components/StatsLeaderboard.svelte';

  type Period = 'all' | 'day' | 'month' | 'year';

  let period: Period = 'year';
  let value = getDefaultValue(period);
  let loading = false;
  let error: string | null = null;
  let rows: LeaderboardRow[] = [];
  let total = 0;
  let page = 1;
  const pageSize = 100;

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
      total = 0;
      return;
    }
    loading = true;
    error = null;
    try {
      const params = new URLSearchParams({ period, page: String(page), page_size: String(pageSize) });
      if (period !== 'all') {
        params.set('value', value);
      }
      const response = await fetch(`/api/v1/stats/tracks?${params.toString()}`);
      if (!response.ok) {
        throw new Error('Kon de nummers niet laden');
      }
      const data: {
        items: { track: string; count: number }[];
        total: number;
      } = await response.json();
      rows = data.items.map((item) => ({ label: item.track, count: item.count }));
      total = data.total;
    } catch (err) {
      error = err instanceof Error ? err.message : 'Onbekende fout';
      rows = [];
      total = 0;
    } finally {
      loading = false;
    }
  }

  function onPeriodChange(event: Event) {
    period = (event.target as HTMLSelectElement).value as Period;
    value = getDefaultValue(period);
    page = 1;
    loadData();
  }

  function onValueChange(event: Event) {
    value = (event.target as HTMLInputElement).value;
    page = 1;
    loadData();
  }

  function changePage(newPage: number) {
    if (newPage < 1 || newPage > totalPages) {
      return;
    }
    page = newPage;
    loadData();
  }

  $: totalPages = Math.max(1, Math.ceil(total / pageSize));
  $: showingStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  $: showingEnd = total === 0 ? 0 : Math.min(total, page * pageSize);

  onMount(() => {
    loadData();
  });
</script>

<section class="page">
  <header>
    <h2>Meest geluisterde nummers</h2>
    <p>Zie welke tracks je maar blijft draaien.</p>
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
      <StatsLeaderboard {rows} labelHeading="Nummer" />
      <footer class="pagination">
        {#if total === 0}
          <span>Geen data beschikbaar voor deze periode.</span>
        {:else}
          <span>Toont {showingStart}–{showingEnd} van {total}</span>
        {/if}
        <div class="pager-controls">
          <button type="button" on:click={() => changePage(page - 1)} disabled={page === 1}>
            Vorige pagina
          </button>
          <span>Pagina {page} van {totalPages}</span>
          <button
            type="button"
            on:click={() => changePage(page + 1)}
            disabled={page === totalPages || total === 0}
          >
            Volgende pagina
          </button>
        </div>
      </footer>
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
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .status {
    color: rgba(255, 255, 255, 0.75);
  }

  .status.error {
    color: #ff8080;
  }

  .pagination {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.75rem;
    font-size: 0.9rem;
    color: rgba(255, 255, 255, 0.75);
  }

  .pager-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .pager-controls button {
    background: rgba(255, 255, 255, 0.08);
    border: none;
    padding: 0.5rem 0.75rem;
    border-radius: 0.75rem;
    color: var(--text-color);
    cursor: pointer;
  }

  .pager-controls button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
