<script lang="ts">
  import { onMount } from 'svelte';
  import { Bell, Trash2, CheckCircle, Clock } from 'lucide-svelte';

  export let API_BASE: string;
  export let getHeaders: () => any;
  export let onMessage: (m: string) => void;
  export let onError: (e: string) => void;
  export let config: any;

  let notifications: any[] = [];
  let loading = false;
  let ntfyUrl = "";
  let ntfyTopic = "";

  async function fetchNotifications() {
    loading = true;
    try {
      const res = await fetch(`${API_BASE}/api/notifications`, { headers: getHeaders() });
      if (res.ok) {
        notifications = await res.json();
      }
    } catch (err) {
      console.error(err);
      onError("Kon meldingen niet ophalen.");
    } finally {
      loading = false;
    }
  }

  async function deleteNotification(id: number) {
    try {
      const res = await fetch(`${API_BASE}/api/notifications/${id}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        notifications = notifications.filter(n => n.id !== id);
      }
    } catch (err) {
      onError("Kon melding niet verwijderen.");
    }
  }

  async function clearAll() {
    if (!confirm("Weet je zeker dat je alle meldingen wilt wissen?")) return;
    try {
      const res = await fetch(`${API_BASE}/api/notifications`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        notifications = [];
        onMessage("Alle meldingen gewist.");
      }
    } catch (err) {
      onError("Kon meldingen niet wissen.");
    }
  }

  function formatDate(dateStr: string) {
    const date = new Date(dateStr);
    return date.toLocaleString('nl-NL');
  }

  onMount(() => {
    fetchNotifications();
    ntfyUrl = config.notify_url || "https://ntfy.teunschriks.nl/";
    ntfyTopic = config.notify_topic || "music-management";
  });
</script>

<div class="flex flex-col gap-8">
  <div class="flex justify-between items-end">
    <div>
      <h1 class="text-4xl font-black mb-2 flex items-center gap-4">
        <Bell size={40} class="text-spotify-green" />
        Meldingen
      </h1>
      <p class="text-spotify-lightgray">Berichten van automatische processen zoals SoundCloud downloads.</p>
    </div>
    
    <div class="flex gap-4">
      <button 
        on:click={fetchNotifications}
        class="bg-white text-black font-bold py-3 px-8 rounded-full hover:scale-105 transition-all text-sm uppercase tracking-wider"
      >
        Vernieuwen
      </button>
      {#if notifications.length > 0}
        <button 
          on:click={clearAll}
          class="bg-red-600 text-white font-bold py-3 px-8 rounded-full hover:scale-105 transition-all text-sm uppercase tracking-wider flex items-center gap-2"
        >
          <Trash2 size={16} />
          Alles wissen
        </button>
      {/if}
    </div>
  </div>

  <div class="bg-black bg-opacity-40 rounded-xl p-6 border border-white border-opacity-10">
    <h3 class="text-xl font-bold mb-4 flex items-center gap-2">
      <CheckCircle size={20} class="text-spotify-green" />
      ntfy.sh Abonnement
    </h3>
    <p class="text-sm text-spotify-lightgray mb-4">
      Je kunt je ook rechtstreeks abonneren op meldingen via de ntfy.sh app of website:
    </p>
    <div class="bg-spotify-gray p-4 rounded-lg flex justify-between items-center border border-white border-opacity-5">
      <code class="text-spotify-green font-mono">{ntfyUrl}{ntfyTopic}</code>
      <a 
        href="{ntfyUrl}{ntfyTopic}" 
        target="_blank" 
        class="text-xs font-bold hover:underline uppercase"
      >
        Openen in ntfy.sh
      </a>
    </div>
  </div>

  <div class="grid gap-4">
    {#if loading && notifications.length === 0}
      <div class="text-center py-20 text-spotify-lightgray">Meldingen laden...</div>
    {:else if notifications.length === 0}
      <div class="text-center py-20 bg-black bg-opacity-20 rounded-xl border border-dashed border-white border-opacity-10">
        <Bell size={48} class="mx-auto mb-4 text-spotify-gray" />
        <p class="text-spotify-lightgray">Geen nieuwe meldingen.</p>
      </div>
    {:else}
      {#each notifications as notification}
        <div class="bg-black bg-opacity-40 hover:bg-opacity-60 transition-all rounded-xl p-5 border border-white border-opacity-10 group relative">
          <div class="flex justify-between items-start mb-2">
            <h4 class="font-bold text-lg text-white pr-10">{notification.title}</h4>
            <span class="text-xs text-spotify-lightgray flex items-center gap-1">
              <Clock size={12} />
              {formatDate(notification.created_at)}
            </span>
          </div>
          <div class="text-spotify-lightgray whitespace-pre-wrap font-mono text-sm bg-black bg-opacity-20 p-3 rounded border border-white border-opacity-5">
            {notification.message}
          </div>
          
          <button 
            on:click={() => deleteNotification(notification.id)}
            class="absolute top-5 right-5 text-spotify-lightgray hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
            title="Verwijderen"
          >
            <Trash2 size={18} />
          </button>
        </div>
      {/each}
    {/if}
  </div>
</div>
