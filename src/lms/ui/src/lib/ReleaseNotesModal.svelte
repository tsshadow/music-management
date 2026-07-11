<script>
  import Modal from './Modal.svelte';
  import { activeModal } from './store.js';

  /** @type {{ releases: Array }} */
  let { releases = [] } = $props();

  function close() {
    activeModal.set(null);
  }
</script>

<Modal title="What's New in LMS" onclose={close}>
  <div class="flex flex-col gap-8">
    <p class="text-[#b3b3b3]">A new version of LMS has been detected! Here are the key changes:</p>
    
    <div class="flex flex-col gap-8">
      {#each releases as release}
        <div class="border-l-4 border-[#1DB954] pl-6 py-2">
          <div class="flex items-baseline gap-4 mb-4">
            <h3 class="text-white text-2xl font-bold">{release.version}</h3>
            <span class="text-sm text-[#b3b3b3] font-medium">{release.date}</span>
          </div>
          
          <div class="space-y-6">
            {#each Object.entries(release.notes) as [category, items]}
              <div>
                <span class="text-[#1DB954] uppercase text-xs font-black tracking-widest">{category}</span>
                <ul class="mt-2 space-y-2">
                  {#each items as item}
                    <li class="text-[#e5e5e5] leading-relaxed flex gap-3">
                      <span class="text-[#1DB954] mt-1.5">•</span>
                      <span>{item}</span>
                    </li>
                  {/each}
                </ul>
              </div>
            {/each}
          </div>
        </div>
      {/each}
    </div>

    <div class="mt-4 flex justify-end">
        <button 
            class="bg-[#1DB954] text-black font-bold py-3 px-8 rounded-full hover:scale-105 transition-transform active:scale-95 cursor-pointer"
            onclick={close}
        >
            Got it
        </button>
    </div>
  </div>
</Modal>
