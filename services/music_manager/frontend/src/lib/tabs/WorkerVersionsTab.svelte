<script lang="ts">
  import { ExternalLink } from 'lucide-svelte';
  
  export let versions: any;
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header>
    <h2 class="text-4xl font-extrabold mb-2">📟 System Versions</h2>
    <p class="text-spotify-lightgray">Centraal overzicht van alle draaiende service versies.</p>
  </header>

  <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
    {#each Object.entries(versions) as [name, version]}
      <div class="bg-spotify-gray p-6 rounded-xl border border-white border-opacity-5 flex flex-col gap-1">
        <span class="text-xs font-bold text-spotify-lightgray uppercase tracking-wider">{name}</span>
        <span class="text-xl font-mono {version === 'offline' ? 'text-red-500' : 'text-spotify-green'}">
          {version}
        </span>
      </div>
    {/each}
  </div>

  <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
    <div class="bg-black bg-opacity-20 p-6 rounded-xl border border-spotify-gray border-dashed md:col-span-2">
      <h3 class="font-bold mb-2 flex items-center gap-2 text-spotify-lightgray">
        <ExternalLink size={16} /> Externe Referenties
      </h3>
      <ul class="text-sm space-y-2 text-spotify-lightgray">
        <li>LMS: <span class="text-white">{versions.lms || 'Niet gedetecteerd'}</span></li>
        <li>Ultrasonic APK: <span class="text-white">{versions.ultrasonic || 'Niet gevonden'}</span></li>
      </ul>
    </div>
  </div>
</section>
