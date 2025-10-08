<script lang="ts">
  export type ListenRow = {
    id: number;
    listened_at: string;
    track_title: string;
    artists: string;
    album_title: string | null;
    genres: string | null;
    source: string;
  };

  export let listens: ListenRow[] = [];

  function formatTime(value: string) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return date.toLocaleString();
  }
</script>

<table>
  <thead>
    <tr>
      <th>Time</th>
      <th>Title</th>
      <th>Artists</th>
      <th>Album</th>
      <th>Genres</th>
      <th>Source</th>
    </tr>
  </thead>
  <tbody>
    {#if listens.length === 0}
      <tr>
        <td colspan="6" class="empty">No listens yet</td>
      </tr>
    {:else}
      {#each listens as listen (listen.id)}
        <tr>
          <td>{formatTime(listen.listened_at)}</td>
          <td>{listen.track_title}</td>
          <td>{listen.artists}</td>
          <td>{listen.album_title ?? '—'}</td>
          <td>{listen.genres ?? '—'}</td>
          <td>{listen.source}</td>
        </tr>
      {/each}
    {/if}
  </tbody>
</table>

<style>
  table {
    width: 100%;
    border-collapse: collapse;
    color: var(--text-color);
    font-size: 0.95rem;
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

  tbody tr:hover {
    background: rgba(255, 255, 255, 0.03);
  }

  .empty {
    text-align: center;
    padding: 2rem 1rem;
    color: rgba(255, 255, 255, 0.6);
  }
</style>
