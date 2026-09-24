<script>
  /**
   * The runtime configuration, rendered from the schema the backend describes.
   *
   * Every field comes from `GET /api/config/fields` with its type, group, description
   * and current value, so a setting added in `config_store.py` shows up here without
   * a frontend change. Saving posts only what differs.
   *
   * Secrets arrive masked and are never sent back unless retyped — see
   * `configFields.js` and `ConfigStore.SECRET_SENTINEL`. Fields marked `read_only`
   * (the database connection) are shown disabled: the environment sets them.
   */
  import { onMount } from 'svelte';
  import { RefreshCw, Save, Eye, EyeOff } from '@lucide/svelte';

  import { SECRET_SENTINEL, changedUpdates, groupFields } from '../configFields.js';

  let { API_BASE, getHeaders, onMessage, onError } = $props();

  let fields = $state([]);
  let draft = $state({});
  let loading = $state(false);
  let saving = $state(false);
  let revealed = $state({});

  const groups = $derived(groupFields(fields));
  const pending = $derived(changedUpdates(fields, draft));
  const pendingCount = $derived(Object.keys(pending).length);

  async function load() {
    loading = true;
    try {
      const res = await fetch(`${API_BASE}/api/config/fields`, { headers: getHeaders() });
      if (!res.ok) {
        onError?.(res.status === 403
          ? 'Je hebt geen rechten om de configuratie te bekijken.'
          : 'De configuratie kon niet worden geladen.');
        return;
      }
      fields = await res.json();
      draft = Object.fromEntries(fields.map((field) => [field.key, field.value]));
    } catch (e) {
      onError?.(e.message);
    } finally {
      loading = false;
    }
  }

  async function save() {
    if (!pendingCount) return;
    saving = true;
    try {
      const res = await fetch(`${API_BASE}/api/config/`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({ updates: pending })
      });
      const body = await res.json().catch(() => null);
      if (!res.ok) {
        onError?.((body && body.detail) || 'Opslaan is niet gelukt.');
        return;
      }
      onMessage?.(`${pendingCount} instelling${pendingCount === 1 ? '' : 'en'} opgeslagen.`);
      await load();
      revealed = {};
    } catch (e) {
      onError?.(e.message);
    } finally {
      saving = false;
    }
  }

  onMount(load);
</script>

<div class="flex flex-col gap-6">
  <header class="flex items-center justify-between gap-4 flex-wrap">
    <div>
      <h2 class="text-2xl font-bold m-0">Configuratie</h2>
      <p class="text-sm text-muma-spotify-text mt-1 mb-0">
        Draaiende instellingen. Wachtwoorden en tokens worden gemaskeerd getoond; laat ze staan om
        ze ongemoeid te laten.
      </p>
    </div>
    <div class="flex items-center gap-2">
      <button
        class="flex items-center gap-2 bg-muma-spotify-light hover:bg-[#3e3e3e] text-white rounded px-4 py-2 text-sm border-none cursor-pointer"
        onclick={load}
        disabled={loading || saving}
      >
        <RefreshCw size={16} /> Herladen
      </button>
      <button
        class="flex items-center gap-2 bg-brand text-black font-bold rounded px-4 py-2 text-sm border-none cursor-pointer disabled:opacity-40"
        onclick={save}
        disabled={!pendingCount || saving}
      >
        <Save size={16} />
        {pendingCount ? `${pendingCount} opslaan` : 'Opslaan'}
      </button>
    </div>
  </header>

  {#if loading && !fields.length}
    <p class="text-muma-spotify-text">Laden…</p>
  {:else}
    {#each groups as group (group.name)}
      <section>
        <h3 class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text m-0 mb-3">
          {group.name}
        </h3>
        <div class="flex flex-col gap-4">
          {#each group.fields as field (field.key)}
            <div class="bg-muma-spotify-light rounded p-4">
              <div class="flex items-start justify-between gap-4 flex-wrap">
                <label class="font-bold text-sm font-mono" for={`cfg-${field.key}`}>
                  {field.key}
                </label>
                {#if field.key in pending}
                  <span class="text-[11px] text-brand font-bold uppercase tracking-wider">gewijzigd</span>
                {/if}
              </div>
              {#if field.description}
                <p class="text-xs text-muma-spotify-text mt-1 mb-3">{field.description}</p>
              {/if}
              {#if field.read_only}
                <p class="text-[11px] text-muma-spotify-text mt-0 mb-2">
                  Alleen-lezen: deze waarde komt uit de omgeving van de container.
                </p>
              {/if}

              {#if field.type === 'boolean'}
                <label class="flex items-center gap-2 text-sm cursor-pointer">
                  <input id={`cfg-${field.key}`} type="checkbox" disabled={field.read_only} bind:checked={draft[field.key]} />
                  {draft[field.key] ? 'Aan' : 'Uit'}
                </label>
              {:else if field.type === 'integer' || field.type === 'number'}
                <input
                  id={`cfg-${field.key}`}
                  type="number"
                  class="w-full bg-muma-spotify-dark border-none rounded px-3 py-2 text-sm text-white"
                  disabled={field.read_only}
                  bind:value={draft[field.key]}
                />
              {:else if field.secret}
                <div class="flex gap-2">
                  <input
                    id={`cfg-${field.key}`}
                    type={revealed[field.key] ? 'text' : 'password'}
                    class="flex-1 bg-muma-spotify-dark border-none rounded px-3 py-2 text-sm text-white font-mono"
                    disabled={field.read_only}
                    bind:value={draft[field.key]}
                  />
                  <button
                    class="bg-transparent border-none text-muma-spotify-text hover:text-white cursor-pointer px-2"
                    onclick={() => (revealed[field.key] = !revealed[field.key])}
                    aria-label={revealed[field.key] ? 'Verbergen' : 'Tonen'}
                    type="button"
                  >
                    {#if revealed[field.key]}<EyeOff size={16} />{:else}<Eye size={16} />{/if}
                  </button>
                </div>
                {#if draft[field.key] === SECRET_SENTINEL}
                  <p class="text-[11px] text-muma-spotify-text mt-2 mb-0">
                    Er staat een waarde ingesteld. Typ een nieuwe om hem te vervangen, of maak het
                    veld leeg om hem te wissen.
                  </p>
                {/if}
              {:else}
                <input
                  id={`cfg-${field.key}`}
                  type="text"
                  class="w-full bg-muma-spotify-dark border-none rounded px-3 py-2 text-sm text-white"
                  disabled={field.read_only}
                  bind:value={draft[field.key]}
                />
              {/if}
            </div>
          {/each}
        </div>
      </section>
    {/each}
  {/if}
</div>
