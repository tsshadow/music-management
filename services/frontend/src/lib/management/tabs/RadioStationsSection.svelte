<script>
  /**
   * Beheer's list of live stations from outside MuMa: add, change, take off the air and remove.
   * The server never opens the address. A device connects to the broadcaster itself.
   */
  import { onMount } from 'svelte';
  import { t } from '../../i18n/index.js';
  import { Plus, Trash2, Play, Pause } from '@lucide/svelte';
  import { slugify } from '../radioChannels.js';

  let { API_BASE, getHeaders, onMessage, onError } = $props();

  let stations = $state([]);
  let saving = $state(false);
  // The station being edited, or 'new'. Its slug is what the API keys on, so it is fixed once a
  // station exists.
  let editing = $state(null);
  let form = $state({ name: '', slug: '', stream_url: '', sort_order: 0 });

  async function fetchStations() {
    try {
      const res = await fetch(`${API_BASE}/api/radio/stations?include_disabled=true`, {
        headers: getHeaders()
      });
      if (res.ok) stations = (await res.json()).stations || [];
      else onError($t('management.radio.stations.loadFailed'));
    } catch {
      onError($t('management.radio.stations.loadFailed'));
    }
  }

  function startNew() {
    editing = 'new';
    form = { name: '', slug: '', stream_url: '', sort_order: (stations.at(-1)?.sort_order ?? 0) + 10 };
  }

  function startEdit(station) {
    editing = station.slug;
    form = {
      name: station.name,
      slug: station.slug,
      stream_url: station.stream_url,
      sort_order: station.sort_order
    };
  }

  async function save() {
    const name = form.name.trim();
    if (!name) {
      onError($t('management.radio.stations.nameRequired'));
      return;
    }
    const isNew = editing === 'new';
    const slug = isNew ? slugify(form.slug || name) : editing;
    if (!slug) {
      onError($t('management.radio.slugRequired'));
      return;
    }
    const fields = { name, stream_url: form.stream_url.trim(), sort_order: Number(form.sort_order) || 0 };
    saving = true;
    try {
      const res = await fetch(
        isNew ? `${API_BASE}/api/radio/stations` : `${API_BASE}/api/radio/stations/${slug}`,
        {
          method: isNew ? 'POST' : 'PUT',
          headers: getHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(isNew ? { slug, ...fields } : fields)
        }
      );
      if (res.ok) {
        onMessage($t('management.radio.stations.saved', { name }));
        editing = null;
        await fetchStations();
      } else {
        const body = await res.json().catch(() => ({}));
        onError(body.detail || $t('management.radio.stations.saveFailed'));
      }
    } catch {
      onError($t('management.radio.stations.saveFailed'));
    } finally {
      saving = false;
    }
  }

  async function toggleEnabled(station) {
    try {
      const res = await fetch(`${API_BASE}/api/radio/stations/${station.slug}`, {
        method: 'PUT',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ enabled: !station.enabled })
      });
      if (res.ok) await fetchStations();
      else onError($t('management.radio.stations.saveFailed'));
    } catch {
      onError($t('management.radio.stations.saveFailed'));
    }
  }

  async function remove(station) {
    if (!confirm($t('management.radio.stations.confirmDelete', { name: station.name }))) return;
    try {
      const res = await fetch(`${API_BASE}/api/radio/stations/${station.slug}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.radio.stations.deleted', { name: station.name }));
        await fetchStations();
      } else {
        onError($t('management.radio.stations.deleteFailed'));
      }
    } catch {
      onError($t('management.radio.stations.deleteFailed'));
    }
  }

  onMount(fetchStations);
</script>

<div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
  <div class="p-4 flex items-center justify-between gap-4">
    <h3 class="text-sm font-bold">{$t('management.radio.stations.title')}</h3>
    <button
      onclick={startNew}
      class="bg-brand text-black px-4 py-2 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-2"
    >
      <Plus size={14} /> {$t('management.radio.stations.new')}
    </button>
  </div>
  <div class="overflow-x-auto">
    <table class="w-full text-left text-sm">
      <tbody class="divide-y divide-muma-spotify-panel/30">
        {#each stations as station (station.slug)}
          <tr class="hover:bg-white/5 transition-colors">
            <td class="p-4">
              <div class="font-bold">{station.name}</div>
              <div class="text-[10px] text-muma-spotify-text break-all">{station.stream_url}</div>
              {#if !station.enabled}
                <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-white/10 text-muma-spotify-text">
                  {$t('management.radio.disabled')}
                </span>
              {/if}
            </td>
            <td class="p-4 text-right">
              <div class="flex justify-end gap-2">
                <button
                  onclick={() => startEdit(station)}
                  class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105"
                >
                  {$t('management.radio.edit')}
                </button>
                <button
                  onclick={() => toggleEnabled(station)}
                  class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                >
                  {#if station.enabled}<Pause size={14} />{:else}<Play size={14} />{/if}
                  {station.enabled ? $t('management.radio.takeOffAir') : $t('management.radio.putOnAir')}
                </button>
                <button
                  onclick={() => remove(station)}
                  aria-label={$t('common.remove')}
                  class="bg-red-500/10 text-red-500 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            </td>
          </tr>
        {:else}
          <tr><td class="p-4 text-muma-spotify-text">{$t('management.radio.stations.empty')}</td></tr>
        {/each}
      </tbody>
    </table>
  </div>

  {#if editing}
    <div class="p-6 space-y-4 border-t border-white/5">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <label class="flex flex-col gap-1 text-xs text-muma-spotify-text">
          {$t('management.radio.name')}
          <input
            bind:value={form.name}
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
          />
        </label>
        {#if editing === 'new'}
          <label class="flex flex-col gap-1 text-xs text-muma-spotify-text">
            {$t('management.radio.slug')}
            <input
              bind:value={form.slug}
              placeholder={slugify(form.name)}
              class="bg-muma-spotify-dark border border-muma-spotify-panel rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
            />
          </label>
        {/if}
        <label class="flex flex-col gap-1 text-xs text-muma-spotify-text md:col-span-2">
          {$t('management.radio.stations.streamUrl')}
          <input
            bind:value={form.stream_url}
            placeholder="https://"
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
          />
        </label>
        <label class="flex flex-col gap-1 text-xs text-muma-spotify-text">
          {$t('management.radio.stations.sortOrder')}
          <input
            type="number"
            bind:value={form.sort_order}
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
          />
        </label>
      </div>
      <div class="flex justify-end gap-2">
        <button
          onclick={() => (editing = null)}
          class="bg-white/10 text-white px-4 py-2 rounded-full font-bold text-xs transition-transform hover:scale-105"
        >
          {$t('common.cancel')}
        </button>
        <button
          onclick={save}
          disabled={saving}
          class="bg-brand text-black px-4 py-2 rounded-full font-bold text-xs transition-transform hover:scale-105 disabled:opacity-50"
        >
          {$t('common.save')}
        </button>
      </div>
    </div>
  {/if}
</div>
