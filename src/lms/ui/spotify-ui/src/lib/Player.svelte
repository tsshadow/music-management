<script>
  import { currentTrack, isPlaying } from './store.js';
</script>

<footer class="h-24 bg-spotify-dark border-t border-spotify-light flex items-center px-4 justify-between z-10">
  <!-- Track Info -->
  <div class="flex items-center gap-4 w-1/3">
    {#if $currentTrack}
      <div class="w-14 h-14 bg-spotify-light rounded-sm overflow-hidden flex-shrink-0">
        <img src="/rest/getCoverArt?id={$currentTrack.coverArt}&u=admin&t=admin&s=salt&v=1.16.1&c=spotify-ui" alt="Cover" class="w-full h-full object-cover" />
      </div>
      <div class="truncate">
        <div class="text-sm font-semibold hover:underline cursor-pointer truncate">{$currentTrack.title}</div>
        <div class="text-xs text-spotify-text hover:underline cursor-pointer truncate">{$currentTrack.artist}</div>
      </div>
      <button class="text-spotify-text hover:text-white ml-2">❤</button>
    {:else}
       <div class="text-spotify-text text-sm italic">Geen nummer geselecteerd</div>
    {/if}
  </div>

  <!-- Player Controls -->
  <div class="flex flex-col items-center max-w-lg w-full">
    <div class="flex items-center gap-6 mb-2">
      <button class="text-spotify-text hover:text-white text-xs">SHUFFLE</button>
      <button class="text-spotify-text hover:text-white text-xs">PREV</button>
      <button 
        on:click={() => isPlaying.update(v => !v)}
        class="bg-white text-black w-8 h-8 rounded-full flex items-center justify-center hover:scale-105 transition"
      >
        {$isPlaying ? '||' : '▶'}
      </button>
      <button class="text-spotify-text hover:text-white text-xs">NEXT</button>
      <button class="text-spotify-text hover:text-white text-xs">REPEAT</button>
    </div>
    <div class="w-full flex items-center gap-2 text-xs text-spotify-text font-mono">
      <span>0:00</span>
      <div class="h-1 flex-1 bg-spotify-light rounded-full overflow-hidden">
        <div class="h-full bg-spotify-green w-1/3"></div>
      </div>
      <span>3:45</span>
    </div>
  </div>

  <!-- Volume -->
  <div class="w-1/3 flex justify-end items-center gap-3">
    <button class="text-spotify-text text-xs">VOL</button>
    <div class="w-24 h-1 bg-spotify-light rounded-full overflow-hidden">
        <div class="h-full bg-white w-1/2 hover:bg-spotify-green transition"></div>
    </div>
  </div>
</footer>
