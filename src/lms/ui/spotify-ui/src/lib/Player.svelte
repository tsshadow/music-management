<script>
  import { onMount } from 'svelte';
  import { currentTrack, playerState, audio, authParams, credentials } from './store.js';

  let audioElement;

  function togglePlay() {
    if (audioElement.paused) {
      audioElement.play().catch(e => console.error("Playback failed", e));
    } else {
      audioElement.pause();
    }
  }

  function handleTimeUpdate() {
    playerState.update(s => ({ ...s, progress: audioElement.currentTime }));
  }

  function handleLoadedMetadata() {
    playerState.update(s => ({ ...s, duration: audioElement.duration }));
  }

  function handlePlay() {
    playerState.update(s => ({ ...s, playing: true }));
  }

  function handlePause() {
    playerState.update(s => ({ ...s, playing: false }));
  }

  function handleVolumeChange() {
    playerState.update(s => ({ ...s, volume: audioElement.volume * 100 }));
  }

  function seek(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percentage = x / rect.width;
    audioElement.currentTime = percentage * audioElement.duration;
  }

  function changeVolume(e) {
      const rect = e.currentTarget.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const vol = Math.max(0, Math.min(1, x / rect.width));
      audioElement.volume = vol;
  }

  function formatTime(seconds) {
    if (isNaN(seconds)) return "0:00";
    const min = Math.floor(seconds / 60);
    const sec = Math.floor(seconds % 60);
    return `${min}:${sec < 10 ? '0' : ''}${sec}`;
  }

  $: track = $currentTrack;
  $: playing = $playerState.playing;
  $: progress = $playerState.progress;
  $: duration = $playerState.duration;
  $: volume = $playerState.volume;
  $: coverUrl = track?.coverArt ? `/rest/getCoverArt?id=${track.coverArt}&size=100&${$authParams}` : '/spotify/default-cover.png';
  $: streamUrl = track?.id ? `/rest/stream?id=${track.id}&${$authParams}` : '';

  $: if (audioElement && track) {
      // Audio element source will update via streamUrl
      // We might want to auto-play when track changes
      audioElement.play().catch(() => {});
  }

  onMount(() => {
    audio.set(audioElement);
    audioElement.volume = volume / 100;
  });
</script>

<audio
  bind:this={audioElement}
  src={streamUrl}
  on:timeupdate={handleTimeUpdate}
  on:loadedmetadata={handleLoadedMetadata}
  on:play={handlePlay}
  on:pause={handlePause}
  on:volumechange={handleVolumeChange}
></audio>

<footer class="player">
  <div class="current-track">
    {#if track}
      <img src={coverUrl} alt={track.title} />
      <div class="track-info">
        <div class="name">{track.title}</div>
        <div class="artist">{track.artist}</div>
      </div>
    {/if}
  </div>

  <div class="controls">
    <div class="buttons">
      <button class="shuffle">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M4.5 6.307a.75.75 0 1 1 0-1.5 5.862 5.862 0 0 1 4.671 2.382l.66.883 5.03 6.717a4.362 4.362 0 0 0 3.471 1.769h1.918a.75.75 0 1 1 0 1.5h-1.918a5.862 5.862 0 0 1-4.671-2.381l-.66-.883-5.03-6.717a4.362 4.362 0 0 0-3.471-1.77H4.5zM14.862 8.567l.66-.883A5.862 5.862 0 0 1 20.193 5.3h1.057a.75.75 0 1 1 0 1.5h-1.057a4.362 4.362 0 0 0-3.471 1.768l-.66.883-.16-.214-.132-.176-.908-1.213-.01.014zM4.5 19.193a.75.75 0 1 0 0-1.5h1.057a4.362 4.362 0 0 0 3.471-1.768l.66-.883.908 1.213.14.186.124.166.01-.013.66.883A5.862 5.862 0 0 1 16.208 20.193H4.5z"></path>
        </svg>
      </button>
      <button class="prev">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M11.838 12.767a1 1 0 0 0 0-1.534L4.513 5.32a.6.6 0 0 0-.913.434v12.492a.6.6 0 0 0 .913.434l7.325-5.913zM20.5 5.754a.6.6 0 0 0-.913-.434l-7.325 5.913a1 1 0 0 0 0 1.534l7.325 5.913a.6.6 0 0 0 .913-.434V5.754z"></path>
        </svg>
      </button>
      <button class="play-pause" on:click={togglePlay}>
        {#if playing}
            <svg viewBox="0 0 24 24" width="24" height="24" fill="black">
                <path d="M9 19H7V5h2v14zm8-14h-2v14h2V5z"></path>
            </svg>
        {:else}
            <svg viewBox="0 0 24 24" width="24" height="24" fill="black">
                <path d="M7 6v12l10-6z"></path>
            </svg>
        {/if}
      </button>
      <button class="next">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M11.162 12.767a1 1 0 0 1 0-1.534l7.325-5.913a.6.6 0 0 1 .913.434v12.492a.6.6 0 0 1-.913.434l-7.325-5.913zM2.5 5.754a.6.6 0 0 1 .913-.434l7.325 5.913a1 1 0 0 1 0 1.534l-7.325 5.913a.6.6 0 0 1-.913-.434V5.754z"></path>
        </svg>
      </button>
      <button class="repeat">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <path d="M4.5 12.2a.75.75 0 0 1 .75-.75h14a.75.75 0 0 1 .75.75v1.25a3.25 3.25 0 0 1-3.25 3.25H7.75a.75.75 0 0 1 0-1.5h8.25a1.75 1.75 0 0 0 1.75-1.75v-.5H5.25a.75.75 0 0 1-.75-.75v-1.25zM19.5 11.8a.75.75 0 0 1-.75.75h-14a.75.75 0 0 1-.75-.75v-1.25a3.25 3.25 0 0 1 3.25-3.25h8.5a.75.75 0 0 1 0 1.5h-8.5a1.75 1.75 0 0 0-1.75 1.75v.5h13.25a.75.75 0 0 1 .75.75v1.25z"></path>
        </svg>
      </button>
    </div>
    <div class="progress-bar">
      <span>{formatTime(progress)}</span>
      <div class="slider" on:click={seek}>
          <div class="fill" style="width: {(progress/duration)*100}%"></div>
      </div>
      <span>{formatTime(duration)}</span>
    </div>
  </div>

  <div class="volume">
    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
        <path d="M12.944 3.32a.75.75 0 0 0-1.06 0L5.321 9.882H2.25a.75.75 0 0 0-.75.75v2.736a.75.75 0 0 0 .75.75h3.07l6.564 6.564a.75.75 0 0 0 1.06 0V3.32zM15.422 7.078a.75.75 0 0 1 1.06 0 7 7 0 0 1 0 9.9 1 1 0 0 1-1.06 0 .75.75 0 0 1 0-1.061 5.5 5.5 0 0 0 0-7.778.75.75 0 0 1 0-1.061z"></path>
    </svg>
    <div class="volume-slider" on:click={changeVolume}>
        <div class="fill" style="width: {volume}%"></div>
    </div>
  </div>
</footer>

<style>
  .player {
    display: flex;
    justify-content: space-between;
    align-items: center;
    height: 100%;
    padding: 0 16px;
  }

  .current-track {
    width: 30%;
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .current-track img {
    width: 56px;
    height: 56px;
    border-radius: 4px;
  }

  .track-info .name {
    font-size: 14px;
    font-weight: 500;
  }

  .track-info .artist {
    font-size: 11px;
    color: #b3b3b3;
  }

  .controls {
    width: 40%;
    max-width: 600px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
  }

  .buttons {
    display: flex;
    align-items: center;
    gap: 24px;
  }

  button {
    background: none;
    border: none;
    color: #b3b3b3;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  button:hover {
    color: #fff;
  }

  .play-pause {
    width: 32px;
    height: 32px;
    background-color: #fff;
    border-radius: 50%;
    color: #000;
  }

  .play-pause:hover {
    transform: scale(1.05);
    background-color: #f6f6f6;
  }

  .progress-bar {
    width: 100%;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11px;
    color: #b3b3b3;
  }

  .slider {
    flex: 1;
    height: 4px;
    background-color: #4d4d4d;
    border-radius: 2px;
  }

  .fill {
    height: 100%;
    width: 30%;
    background-color: #fff;
    border-radius: 2px;
  }

  .volume {
    width: 30%;
    display: flex;
    justify-content: flex-end;
    align-items: center;
    gap: 8px;
  }

  .volume-slider {
    width: 100px;
    height: 4px;
    background-color: #4d4d4d;
    border-radius: 2px;
  }
</style>
