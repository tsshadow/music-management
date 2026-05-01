<script>
  import { currentTrack, playerState } from './store.js';

  export let tracks = [];

  function playTrack(track) {
    currentTrack.set(track);
    playerState.set({ playing: true });
  }

  function formatTime(ms) {
    if (!ms) return "0:00";
    const minutes = Math.floor(ms / 60000);
    const seconds = ((ms % 60000) / 1000).toFixed(0);
    return minutes + ":" + (seconds < 10 ? '0' : '') + seconds;
  }
</script>

<table class="track-list">
  <thead>
    <tr>
      <th class="col-index">#</th>
      <th class="col-title">Titel</th>
      <th class="col-album">Album</th>
      <th class="col-duration">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path d="M8 1.5a6.5 6.5 0 100 13 6.5 6.5 0 000-13zM0 8a8 8 0 1116 0A8 8 0 010 8z"></path>
          <path d="M8 4a.5.5 0 01.5.5v3h3a.5.5 0 010 1H8a.5.5 0 01-.5-.5v-4A.5.5 0 018 4z"></path>
        </svg>
      </th>
    </tr>
  </thead>
  <tbody>
    {#each tracks as track, i}
      <tr class:active={$currentTrack?.id === track.id} on:dblclick={() => playTrack(track)}>
        <td class="col-index">
            <span class="index-num">{i + 1}</span>
            <button class="play-btn" on:click={() => playTrack(track)}>
                <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                    <path d="M7 6v12l10-6z"></path>
                </svg>
            </button>
        </td>
        <td class="col-title">
          <div class="title-container">
            {#if track.coverArt}
              <img src="/rest/getCoverArt?id={track.coverArt}&size=40" alt="" />
            {/if}
            <div class="info">
              <span class="name">{track.title}</span>
              <span class="artist">{track.artist}</span>
            </div>
          </div>
        </td>
        <td class="col-album">{track.album || ''}</td>
        <td class="col-duration">{formatTime(track.duration * 1000)}</td>
      </tr>
    {/each}
  </tbody>
</table>

<style>
  .track-list {
    width: 100%;
    border-collapse: collapse;
    color: #b3b3b3;
    font-size: 14px;
  }

  thead {
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  }

  th {
    text-align: left;
    padding: 8px 16px;
    font-weight: 400;
    text-transform: uppercase;
    font-size: 11px;
    letter-spacing: 0.1em;
  }

  td {
    padding: 8px 16px;
    height: 56px;
    vertical-align: center;
  }

  tr:hover {
    background-color: rgba(255, 255, 255, 0.1);
    color: #fff;
  }

  tr.active {
    color: #1db954;
  }

  .col-index {
    width: 50px;
    text-align: right;
    position: relative;
  }

  .index-num {
    display: block;
  }

  tr:hover .index-num {
    display: none;
  }

  .play-btn {
    display: none;
    background: none;
    border: none;
    color: #fff;
    cursor: pointer;
    padding: 0;
  }

  tr:hover .play-btn {
    display: block;
  }

  .title-container {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .title-container img {
    width: 40px;
    height: 40px;
    border-radius: 4px;
  }

  .info {
    display: flex;
    flex-direction: column;
  }

  .name {
    color: #fff;
    font-size: 16px;
    font-weight: 500;
  }

  tr.active .name {
      color: #1db954;
  }

  .artist {
    font-size: 14px;
  }

  .col-duration {
    text-align: right;
    width: 100px;
  }
</style>
