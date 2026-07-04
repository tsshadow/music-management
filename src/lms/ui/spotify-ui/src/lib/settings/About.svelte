<script>
  import { onMount } from 'svelte';
  import { authParams } from '../store.js';

  let version = '...';
  let serverType = '...';
  let isLoading = true;
  let releaseNotes = [];

  /**
   * Fetches server version and metadata.
   */
  async function loadInfo() {
    try {
      const response = await fetch(`/rest/ping?${$authParams}`);
      const data = await response.json();
      const res = data['subsonic-response'];
      if (res) {
        version = res.serverVersion || res.version;
        serverType = res.type || 'LMS';
      }

      const rnResponse = await fetch('/release-notes.json');
      if (rnResponse.ok) {
        releaseNotes = await rnResponse.json();
      }
    } catch (e) {
      console.error(e);
    } finally {
      isLoading = false;
    }
  }

  onMount(loadInfo);
</script>

<section>
  <h3 class="text-2xl font-bold mb-6">About LMS</h3>
  <div class="flex flex-col gap-4 text-[#b3b3b3]">
    <div class="flex items-center gap-6 mb-4">
        <img src="/images/logo.svg" alt="LMS Logo" class="w-24 h-24" on:error={(e) => e.target.src = '/images/spotify-fallback.svg'} />
        <div>
            <h4 class="text-white text-3xl font-bold">Lightweight Music Server</h4>
            <p>Version {version} {serverType !== '...' ? `(${serverType})` : ''}</p>
        </div>
    </div>
    <p>LMS is a fast, feature-rich music streaming server written in C++.</p>
    <p>© 2024-2026 The LMS Project. Distributed under the GPL license.</p>
    
    {#if releaseNotes.length > 0}
      <div class="mt-8">
        <h4 class="text-white text-xl font-bold mb-4">Release Notes</h4>
        <div class="flex flex-col gap-6">
          {#each releaseNotes as release}
            <div class="border-l-2 border-[#1DB954] pl-4">
              <div class="flex items-center gap-3 mb-2">
                <span class="text-white font-bold">{release.version}</span>
                <span class="text-xs text-[#b3b3b3]">{release.date}</span>
              </div>
              <div class="text-sm space-y-3">
                {#each Object.entries(release.notes) as [category, items]}
                  <div>
                    <span class="text-[#1DB954] uppercase text-[10px] font-bold tracking-wider">{category}</span>
                    <ul class="list-disc list-inside mt-1 text-[#e5e5e5]">
                      {#each items as item}
                        <li>{item}</li>
                      {/each}
                    </ul>
                  </div>
                {/each}
              </div>
            </div>
          {/each}
        </div>
      </div>
    {/if}

    <div class="mt-6 flex gap-4">
        <a href="https://github.com/epoupon/lms" target="_blank" class="text-white font-bold hover:underline">GitHub</a>
        <a href="https://github.com/epoupon/lms/wiki" target="_blank" class="text-white font-bold hover:underline">Documentation</a>
        <button class="text-white font-bold hover:underline bg-transparent border-none cursor-pointer p-0">License</button>
    </div>
  </div>
</section>
