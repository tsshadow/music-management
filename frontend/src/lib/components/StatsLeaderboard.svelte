<script lang="ts">
  export interface LeaderboardRow {
    label: string;
    count: number;
  }

  export let rows: LeaderboardRow[] = [];
  export let labelHeading: string;

  const medals = ['🥇', '🥈', '🥉'];
</script>

<table class="leaderboard">
  <thead>
    <tr>
      <th>#</th>
      <th>{labelHeading}</th>
      <th>Listens</th>
    </tr>
  </thead>
  <tbody>
    {#if rows.length === 0}
      <tr>
        <td colspan="3" class="empty">No data yet</td>
      </tr>
    {:else}
      {#each rows as row, index}
        <tr class:gold={index === 0} class:silver={index === 1} class:bronze={index === 2}>
          <td class="rank">{index < 3 ? medals[index] : index + 1}</td>
          <td>{row.label}</td>
          <td>{row.count.toLocaleString()}</td>
        </tr>
      {/each}
    {/if}
  </tbody>
</table>

<style>
  .leaderboard {
    width: 100%;
    border-collapse: collapse;
    color: var(--text-color);
  }

  th,
  td {
    padding: 0.75rem 1rem;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    text-align: left;
  }

  thead {
    background: rgba(255, 255, 255, 0.05);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.75rem;
  }

  tbody tr:nth-child(even) {
    background: rgba(255, 255, 255, 0.04);
  }

  tbody tr:hover {
    background: rgba(255, 255, 255, 0.06);
  }

  .rank {
    width: 3rem;
  }

  tbody tr.gold {
    background: linear-gradient(90deg, rgba(255, 215, 0, 0.15), transparent);
  }

  tbody tr.silver {
    background: linear-gradient(90deg, rgba(192, 192, 192, 0.12), transparent);
  }

  tbody tr.bronze {
    background: linear-gradient(90deg, rgba(205, 127, 50, 0.12), transparent);
  }

  .empty {
    text-align: center;
    padding: 2rem 1rem;
    color: rgba(255, 255, 255, 0.6);
  }
</style>
