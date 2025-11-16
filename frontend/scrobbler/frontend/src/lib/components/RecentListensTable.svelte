<script lang="ts">
  import { createEventDispatcher } from 'svelte';

  export type ListenArtist = {
    id: number | null;
    name: string;
  };

  export type ListenRow = {
    id: number;
    listened_at: string;
    track_id: number;
    track_title: string;
    album_id: number | null;
    album_title: string | null;
    album_release_year: number | null;
    artists: ListenArtist[];
    artist_names: string | null;
    genres: string[];
    genre_names: string | null;
    source: string;
    source_track_id?: string | null;
    position_secs?: number | null;
    duration_secs?: number | null;
  };

  export let listens: ListenRow[] = [];

  const dispatch = createEventDispatcher<{
    selectListen: ListenRow;
    selectArtist: { listen: ListenRow; artist: ListenArtist };
    selectAlbum: { listen: ListenRow };
  }>();

  function formatTime(value: string) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }
    return date.toLocaleString();
  }

  function displayAlbum(listen: ListenRow) {
    return listen.album_title ?? '—';
  }

  function displayGenres(listen: ListenRow) {
    return listen.genre_names ?? '—';
  }

  function handleRowClick(listen: ListenRow) {
    dispatch('selectListen', listen);
  }

  function handleRowKeydown(event: KeyboardEvent, listen: ListenRow) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      dispatch('selectListen', listen);
    }
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
        <tr
          class="clickable"
          tabindex="0"
          on:click={() => handleRowClick(listen)}
          on:keydown={(event) => handleRowKeydown(event, listen)}
        >
          <td>{formatTime(listen.listened_at)}</td>
          <td>{listen.track_title}</td>
          <td>
            {#if listen.artists.length === 0}
              —
            {:else}
              {#each listen.artists as artist, index}
                <button
                  type="button"
                  class="link"
                  on:click|stopPropagation={() => dispatch('selectArtist', { listen, artist })}
                >
                  {artist.name}
                </button>{index < listen.artists.length - 1 ? ', ' : ''}
              {/each}
            {/if}
          </td>
          <td>
            {#if listen.album_id && listen.album_title}
              <button
                type="button"
                class="link"
                on:click|stopPropagation={() => dispatch('selectAlbum', { listen })}
              >
                {displayAlbum(listen)}
              </button>
            {:else}
              {displayAlbum(listen)}
            {/if}
          </td>
          <td>{displayGenres(listen)}</td>
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

  tr.clickable {
    cursor: pointer;
  }

  tr.clickable:focus {
    outline: 2px solid var(--accent-color);
    outline-offset: -2px;
  }

  button.link {
    background: none;
    border: none;
    color: var(--accent-color);
    cursor: pointer;
    padding: 0;
    font: inherit;
    text-decoration: underline;
  }

  button.link:hover,
  button.link:focus {
    color: #fff;
  }

  .empty {
    text-align: center;
    padding: 2rem 1rem;
    color: rgba(255, 255, 255, 0.6);
  }
</style>
