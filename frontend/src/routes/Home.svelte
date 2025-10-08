<script lang="ts">
  import { onMount } from 'svelte';
  import KpiCard from '../lib/components/KpiCard.svelte';
  import RecentListensTable, { type ListenRow } from '../lib/components/RecentListensTable.svelte';

  let total = 0;
  let listens: ListenRow[] = [];

  async function loadData() {
    const countRes = await fetch('/api/v1/listens/count');
    if (countRes.ok) {
      const data = await countRes.json();
      total = data.count;
    }
    const recentRes = await fetch('/api/v1/listens/recent?limit=10');
    if (recentRes.ok) {
      listens = await recentRes.json();
    }
  }

  onMount(() => {
    loadData();
  });
</script>

<section class="home">
  <KpiCard label="Total listens" value={total.toLocaleString()} />
  <div class="table-wrapper">
    <RecentListensTable {listens} />
  </div>
</section>

<style>
  .home {
    display: flex;
    flex-direction: column;
    gap: 2rem;
    padding: 0 2rem 4rem;
    align-items: center;
  }

  .table-wrapper {
    width: min(960px, 100%);
    background: rgba(0, 0, 0, 0.15);
    border-radius: 1rem;
    padding: 1rem;
    overflow-x: auto;
  }
</style>
