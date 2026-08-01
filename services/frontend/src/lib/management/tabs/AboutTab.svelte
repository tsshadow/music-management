<script >
  import { t } from '../../i18n/index.js';
  import { onMount } from 'svelte';
  
  export let apiKey;
  export let API_BASE;

  let aboutHtml = $t('common.loading');

  async function fetchAbout() {
    try {
      const res = await fetch(`${API_BASE}/api/about`, {
        headers: { 'X-API-Key': apiKey }
      });
      if (res.ok) {
        aboutHtml = await res.text();
      } else {
        aboutHtml = $t('management.about.loadFailed', { message: res.statusText });
      }
    } catch (e) {
      aboutHtml = $t('management.about.loadFailed', { message: e.message });
    }
  }

  onMount(fetchAbout);
</script>

<section class="animate-in fade-in duration-500">
  <div class="bg-spotify-gray p-8 rounded-xl border border-white border-opacity-5 prose prose-invert max-w-none">
    {@html aboutHtml}
  </div>
</section>
