<script>
  import { onMount } from 'svelte';
  import { t } from '../../i18n/index.js';
  import { Radio, RefreshCw, Plus, Trash2, Play, Pause, Search } from '@lucide/svelte';
  import {
    emptyFilterForm,
    filterToForm,
    formToFilter,
    describeFilter,
    slugify
  } from '../radioChannels.js';

  let { API_BASE, getHeaders, onMessage, onError } = $props();

  let channels = $state([]);
  let loading = $state(false);
  let saving = $state(false);

  // The channel being edited, or 'new'. Its slug is what the API keys on, so it
  // is fixed once a channel exists.
  let editing = $state(null);
  let form = $state({ name: '', slug: '', ...emptyFilterForm() });
  let labelSuggestions = $state([]);

  // Preview belongs to the filter as it stands, so any edit invalidates it.
  let preview = $state(null);
  let previewing = $state(false);

  const filterUnderEdit = $derived(formToFilter(form));
  const previewLabel = $derived(describeFilter(filterUnderEdit, $t('management.radio.wholeLibrary')));

  async function fetchChannels() {
    loading = true;
    try {
      const res = await fetch(`${API_BASE}/api/radio/channels?include_disabled=true`, {
        headers: getHeaders()
      });
      if (res.ok) {
        channels = (await res.json()).channels || [];
      } else {
        onError($t('management.radio.loadFailed'));
      }
    } catch {
      onError($t('management.radio.loadFailed'));
    } finally {
      loading = false;
    }
  }

  async function fetchLabels(query) {
    try {
      const res = await fetch(`${API_BASE}/api/labels?q=${encodeURIComponent(query || '')}`, {
        headers: getHeaders()
      });
      if (res.ok) labelSuggestions = await res.json();
    } catch (err) {
      console.error('Kon labels niet ophalen:', err);
    }
  }

  function startNew() {
    editing = 'new';
    form = { name: '', slug: '', ...emptyFilterForm() };
    preview = null;
  }

  function startEdit(channel) {
    editing = channel.slug;
    form = { name: channel.name, slug: channel.slug, ...filterToForm(channel.filter) };
    preview = null;
  }

  function cancel() {
    editing = null;
    preview = null;
  }

  async function runPreview() {
    previewing = true;
    preview = null;
    try {
      const res = await fetch(`${API_BASE}/api/radio/channels/preview`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ filter: filterUnderEdit })
      });
      const body = await res.json();
      if (res.ok) {
        preview = body;
      } else {
        // An unknown label or genre name lands here, which is the whole point of
        // previewing before saving.
        onError(body.detail || $t('management.radio.previewFailed'));
      }
    } catch {
      onError($t('management.radio.previewFailed'));
    } finally {
      previewing = false;
    }
  }

  async function save() {
    const name = form.name.trim();
    if (!name) {
      onError($t('management.radio.nameRequired'));
      return;
    }
    const filter = filterUnderEdit;
    saving = true;
    try {
      const isNew = editing === 'new';
      const slug = isNew ? slugify(form.slug || name) : editing;
      if (isNew && !slug) {
        onError($t('management.radio.slugRequired'));
        return;
      }
      const res = await fetch(
        isNew ? `${API_BASE}/api/radio/channels` : `${API_BASE}/api/radio/channels/${slug}`,
        {
          method: isNew ? 'POST' : 'PUT',
          headers: getHeaders({ 'Content-Type': 'application/json' }),
          body: JSON.stringify(isNew ? { slug, name, filter } : { name, filter })
        }
      );
      if (res.ok) {
        onMessage($t('management.radio.saved', { name }));
        editing = null;
        preview = null;
        await fetchChannels();
      } else {
        const body = await res.json();
        onError(body.detail || $t('management.radio.saveFailed'));
      }
    } catch {
      onError($t('management.radio.saveFailed'));
    } finally {
      saving = false;
    }
  }

  async function toggleEnabled(channel) {
    try {
      const res = await fetch(`${API_BASE}/api/radio/channels/${channel.slug}`, {
        method: 'PUT',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ enabled: !channel.enabled })
      });
      if (res.ok) await fetchChannels();
      else onError($t('management.radio.saveFailed'));
    } catch {
      onError($t('management.radio.saveFailed'));
    }
  }

  async function remove(channel) {
    if (!confirm($t('management.radio.confirmDelete', { name: channel.name }))) return;
    try {
      const res = await fetch(`${API_BASE}/api/radio/channels/${channel.slug}`, {
        method: 'DELETE',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.radio.deleted', { name: channel.name }));
        if (editing === channel.slug) cancel();
        await fetchChannels();
      } else {
        onError($t('management.radio.deleteFailed'));
      }
    } catch {
      onError($t('management.radio.deleteFailed'));
    }
  }

  onMount(() => {
    fetchChannels();
    fetchLabels('');
  });
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex justify-between items-end flex-wrap gap-4">
    <div>
      <h2 class="text-4xl font-extrabold mb-2 flex items-center gap-3">
        <Radio class="text-brand" size={32} /> {$t('management.tabs.radio')}
      </h2>
      <p class="text-muma-spotify-text">{$t('management.radio.subtitle')}</p>
    </div>
    <div class="flex items-center gap-3">
      <button
        onclick={fetchChannels}
        disabled={loading}
        aria-label={$t('common.refresh')}
        class="text-muma-spotify-text hover:text-white transition-colors disabled:opacity-50"
      >
        <RefreshCw size={18} class={loading ? 'animate-spin' : ''} />
      </button>
      <button
        onclick={startNew}
        class="bg-brand text-black px-4 py-2 rounded-full font-bold text-sm transition-transform hover:scale-105 flex items-center gap-2"
      >
        <Plus size={16} /> {$t('management.radio.newChannel')}
      </button>
    </div>
  </header>

  <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
    <div class="min-h-[120px]">
      {#if loading && channels.length === 0}
        <div class="flex items-center justify-center p-20">
          <RefreshCw class="animate-spin text-brand" size={32} />
        </div>
      {:else if channels.length === 0}
        <div class="flex flex-col items-center justify-center p-20 text-muma-spotify-text">
          <Radio size={48} class="mb-4 opacity-20" />
          <p>{$t('management.radio.empty')}</p>
        </div>
      {:else}
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead>
              <tr class="bg-white/5 text-muma-spotify-text text-[10px] uppercase tracking-wider">
                <th class="p-4">{$t('management.radio.channel')}</th>
                <th class="p-4">{$t('management.radio.plays')}</th>
                <th class="p-4 text-right">{$t('management.genres.actions')}</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-muma-spotify-panel/30">
              {#each channels as channel (channel.slug)}
                <tr class="hover:bg-white/5 transition-colors">
                  <td class="p-4">
                    <div class="font-bold">{channel.name}</div>
                    <div class="text-[10px] text-muma-spotify-text">/{channel.slug}</div>
                    {#if !channel.enabled}
                      <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded bg-white/10 text-muma-spotify-text">
                        {$t('management.radio.disabled')}
                      </span>
                    {/if}
                  </td>
                  <td class="p-4 text-muma-spotify-text">
                    {describeFilter(channel.filter, $t('management.radio.wholeLibrary'))}
                  </td>
                  <td class="p-4 text-right">
                    <div class="flex justify-end gap-2">
                      <button
                        onclick={() => startEdit(channel)}
                        class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105"
                      >
                        {$t('management.radio.edit')}
                      </button>
                      <button
                        onclick={() => toggleEnabled(channel)}
                        class="bg-white/10 text-white px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                      >
                        {#if channel.enabled}<Pause size={14} />{:else}<Play size={14} />{/if}
                        {channel.enabled ? $t('management.radio.takeOffAir') : $t('management.radio.putOnAir')}
                      </button>
                      <button
                        onclick={() => remove(channel)}
                        aria-label={$t('common.remove')}
                        class="bg-red-500/10 text-red-500 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>
  </div>

  {#if editing}
    <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 p-6 space-y-6">
      <h3 class="text-xl font-bold">
        {editing === 'new' ? $t('management.radio.newChannel') : form.name}
      </h3>

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
      </div>

      <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <label class="flex flex-col gap-1 text-xs text-muma-spotify-text">
          {$t('management.radio.label')}
          <input
            bind:value={form.label}
            list="radio-label-suggestions"
            oninput={(e) => fetchLabels(e.currentTarget.value)}
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
          />
          <datalist id="radio-label-suggestions">
            {#each labelSuggestions as suggestion (suggestion.id)}
              <option value={suggestion.name}></option>
            {/each}
          </datalist>
        </label>
        <label class="flex flex-col gap-1 text-xs text-muma-spotify-text">
          {$t('management.radio.genre')}
          <input
            bind:value={form.genre}
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
          />
        </label>
        <label class="flex flex-col gap-1 text-xs text-muma-spotify-text">
          {$t('management.radio.artist')}
          <input
            bind:value={form.artist}
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
          />
        </label>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
        <label class="flex flex-col gap-1 text-xs text-muma-spotify-text">
          {$t('management.radio.durationMin')}
          <input
            type="number"
            min="0"
            bind:value={form.duration_min}
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
          />
        </label>
        <label class="flex flex-col gap-1 text-xs text-muma-spotify-text">
          {$t('management.radio.durationMax')}
          <input
            type="number"
            min="0"
            bind:value={form.duration_max}
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
          />
        </label>
        <label class="flex flex-col gap-1 text-xs text-muma-spotify-text">
          {$t('management.radio.ratingMin')}
          <input
            type="number"
            min="0"
            max="5"
            bind:value={form.rating_min}
            class="bg-muma-spotify-dark border border-muma-spotify-panel rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-brand"
          />
        </label>
        <label class="flex items-center gap-2 text-xs text-muma-spotify-text mt-5">
          <input type="checkbox" bind:checked={form.include_unrated} />
          {$t('management.radio.includeUnrated')}
        </label>
      </div>

      <div class="flex items-center justify-between gap-4 flex-wrap border-t border-white/5 pt-4">
        <div class="text-sm text-muma-spotify-text">
          <span class="font-bold text-white">{previewLabel}</span>
          {#if preview}
            <span class="ml-2">
              {preview.truncated
                ? $t('management.radio.matchedAtLeast', { count: preview.matched })
                : $t('management.radio.matched', { count: preview.matched })}
            </span>
          {/if}
        </div>
        <div class="flex items-center gap-2">
          <button
            onclick={runPreview}
            disabled={previewing}
            class="bg-white/10 text-white px-4 py-2 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-2 disabled:opacity-50"
          >
            <Search size={14} /> {$t('management.radio.preview')}
          </button>
          <button
            onclick={cancel}
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

      {#if preview?.sample?.length}
        <ul class="text-xs text-muma-spotify-text space-y-1">
          {#each preview.sample as track (track.track_id)}
            <li>{track.artist} — {track.title}</li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</section>
