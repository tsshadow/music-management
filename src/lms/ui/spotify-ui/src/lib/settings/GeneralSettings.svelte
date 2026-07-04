<script>
  import { deduplicateEnabled } from '../store.js';

  function toggleDeduplicate() {
    deduplicateEnabled.update(v => !v);
  }
</script>

<div class="p-8 max-w-4xl mx-auto">
  <header class="mb-8">
    <h1 class="text-3xl font-bold mb-2">Algemene Instellingen</h1>
    <p class="text-[#b3b3b3]">Beheer de algemene weergave en het gedrag van de interface.</p>
  </header>

  <section class="bg-[#181818] rounded-lg p-6 flex flex-col gap-6 shadow-lg border border-white/5">
    <div class="flex items-center justify-between">
      <div class="flex flex-col gap-1">
        <h3 class="text-lg font-bold">Deduplicatie</h3>
        <p class="text-sm text-[#b3b3b3]">Verberg dubbele nummers op basis van artiest en titel. Geeft voorkeur aan de hoogste kwaliteit (FLAC > MP3).</p>
      </div>
      <label class="relative inline-flex items-center cursor-pointer">
        <input type="checkbox" class="sr-only peer" checked={$deduplicateEnabled} onchange={toggleDeduplicate}>
        <div class="w-11 h-6 bg-[#333] peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-brand"></div>
      </label>
    </div>
  </section>
</div>

<style>
  .bg-brand {
    background-color: #1ed760;
  }
</style>
