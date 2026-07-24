<script >
  import { onMount } from 'svelte';
  
  export let apiKey;
  export let API_BASE;

  let aboutHtml = 'Loading about content...';

  async function fetchAbout() {
    try {
      const res = await fetch(`${API_BASE}/api/about`, {
        headers: { 'X-API-Key': apiKey }
      });
      if (res.ok) {
        aboutHtml = await res.text();
      } else {
        aboutHtml = 'Failed to load about content: ' + res.statusText;
      }
    } catch (e) {
      aboutHtml = 'Failed to load about content: ' + e.message;
    }
  }

  onMount(fetchAbout);
</script>

<section class="animate-in fade-in duration-500">
  <div class="bg-spotify-gray p-8 rounded-xl border border-white border-opacity-5 prose prose-invert max-w-none">
    {@html aboutHtml}
  </div>
</section>
