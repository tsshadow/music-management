<script>
  import { onMount } from 'svelte';
  import { authParams } from '../store.js';

  let version = '...';
  let serverType = '...';
  let isLoading = true;

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
    <div class="mt-6 flex gap-4">
        <a href="https://github.com/epoupon/lms" target="_blank" class="text-white font-bold hover:underline">GitHub</a>
        <a href="https://github.com/epoupon/lms/wiki" target="_blank" class="text-white font-bold hover:underline">Documentation</a>
        <button class="text-white font-bold hover:underline bg-transparent border-none cursor-pointer p-0">License</button>
    </div>
  </div>
</section>
