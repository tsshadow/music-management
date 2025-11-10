<script lang="ts">
  import { onMount } from 'svelte';

  const API_BASE = import.meta.env.VITE_API_BASE || '/api';

  type ConfigField = {
    key: string;
    type: 'string' | 'boolean' | 'integer';
    group: string;
    description?: string;
    nullable: boolean;
    default: unknown;
    value: unknown;
  };

  let fields: ConfigField[] = [];
  let grouped: { group: string; items: ConfigField[] }[] = [];
  let values: Record<string, any> = {};
  let validation: Record<string, string> = {};
  let dirty: Set<string> = new Set();
  let loading = true;
  let saving = false;
  let error = '';
  let success = '';
  const fieldMap: Map<string, ConfigField> = new Map();
  let expanded = false;

  onMount(() => {
    loadConfig();
  });

  async function loadConfig() {
    loading = true;
    error = '';
    success = '';
    dirty = new Set();
    try {
      const res = await fetch(`${API_BASE}/config`);
      if (!res.ok) {
        throw new Error(`Failed to fetch config: ${res.status}`);
      }
      const data = await res.json();
      const received: ConfigField[] = Array.isArray(data.fields) ? data.fields : [];
      fields = received.map((field) => ({ ...field }));
      fieldMap.clear();
      const newValues: Record<string, any> = {};
      const newValidation: Record<string, string> = {};
      for (const field of fields) {
        fieldMap.set(field.key, field);
        const initial = normaliseValue(field, field.value);
        newValues[field.key] = initial;
        newValidation[field.key] = validateField(field, initial);
      }
      values = newValues;
      validation = newValidation;
      updateGroups();
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to load configuration';
      fields = [];
      grouped = [];
      values = {};
      validation = {};
    } finally {
      loading = false;
    }
  }

  function normaliseValue(field: ConfigField, value: unknown) {
    if (field.type === 'boolean') {
      return Boolean(value);
    }
    if (field.type === 'integer') {
      if (value === null || value === undefined) return '';
      return typeof value === 'number' ? value : Number(value) || '';
    }
    return value ?? '';
  }

  function updateGroups() {
    const groups = new Map<string, ConfigField[]>();
    for (const field of fields) {
      const groupName = field.group || 'General';
      if (!groups.has(groupName)) {
        groups.set(groupName, []);
      }
      groups.get(groupName)?.push(field);
    }
    grouped = Array.from(groups.entries()).map(([group, items]) => ({ group, items }));
  }

  function setDirty(key: string) {
    dirty = new Set(dirty);
    dirty.add(key);
    success = '';
  }

  function handleChange(field: ConfigField, rawValue: any) {
    let newValue: any;
    if (field.type === 'boolean') {
      newValue = Boolean(rawValue);
    } else if (field.type === 'integer') {
      newValue = rawValue === '' ? '' : rawValue;
    } else {
      newValue = rawValue ?? '';
    }
    values = { ...values, [field.key]: newValue };
    validation = { ...validation, [field.key]: validateField(field, newValue) };
    setDirty(field.key);
  }

  function validateField(field: ConfigField, value: any): string {
    if (field.type === 'integer') {
      if (value === '' || value === null || value === undefined) {
        return field.nullable ? '' : 'Value required';
      }
      const stringValue = typeof value === 'number' ? String(value) : String(value ?? '').trim();
      if (!/^[-+]?\d+$/.test(stringValue)) {
        return 'Must be an integer';
      }
    }
    return '';
  }

  function parseForUpdate(field: ConfigField, value: any) {
    if (field.type === 'boolean') {
      return Boolean(value);
    }
    if (field.type === 'integer') {
      if (value === '' || value === null || value === undefined) {
        return field.nullable ? null : 0;
      }
      if (typeof value === 'number') return value;
      return Number(String(value).trim());
    }
    if (value === null || value === undefined) {
      return '';
    }
    return String(value);
  }

  async function save() {
    error = '';
    success = '';
    if (!dirty.size) {
      return;
    }
    if (Object.values(validation).some((message) => message)) {
      error = 'Fix validation errors before saving.';
      return;
    }
    const updates: Record<string, any> = {};
    for (const key of dirty) {
      const field = fieldMap.get(key);
      if (!field) continue;
      updates[key] = parseForUpdate(field, values[key]);
    }

    saving = true;
    try {
      const res = await fetch(`${API_BASE}/config`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates }),
      });
      if (!res.ok) {
        const details = await res.json().catch(() => ({}));
        const detail = details?.detail ?? 'Failed to update configuration';
        throw new Error(detail);
      }
      const payload = await res.json();
      const updated = payload?.values ?? {};
      const newValues: Record<string, any> = { ...values };
      const newValidation: Record<string, string> = { ...validation };
      for (const [key, value] of Object.entries(updated)) {
        const field = fieldMap.get(key);
        if (!field) continue;
        field.value = value;
        const normalised = normaliseValue(field, value);
        newValues[key] = normalised;
        newValidation[key] = validateField(field, normalised);
      }
      values = newValues;
      validation = newValidation;
      fields = [...fields];
      updateGroups();
      dirty = new Set();
      success = 'Configuration updated.';
    } catch (err) {
      error = err instanceof Error ? err.message : 'Failed to update configuration';
    } finally {
      saving = false;
    }
  }
</script>

<div class="space-y-4 rounded border border-green-700/40 bg-black/60 p-4">
  <div class="flex flex-wrap items-center justify-between gap-4">
    <button
      class="flex items-center gap-2 rounded border border-green-600 px-4 py-2 text-left text-green-200 transition hover:bg-green-600/20"
      on:click={() => (expanded = !expanded)}
      aria-expanded={expanded}
    >
      <span class="text-2xl font-semibold text-green-300">Configuration</span>
      <span class={`transition-transform ${expanded ? 'rotate-180' : ''}`}>⌄</span>
    </button>
    {#if expanded}
      <button
        class="rounded bg-green-600 px-4 py-2 font-semibold text-black shadow disabled:opacity-50"
        on:click={save}
        disabled={saving || !dirty.size}
      >
        {saving ? 'Saving…' : 'Save changes'}
      </button>
    {/if}
  </div>

  {#if error}
    <div class="rounded border border-red-500/60 bg-red-900/40 p-3 text-sm text-red-200">{error}</div>
  {/if}
  {#if success}
    <div class="rounded border border-green-500/60 bg-green-900/40 p-3 text-sm text-green-200">
      {success}
    </div>
  {/if}

  {#if expanded}
    {#if loading}
      <p class="text-sm text-green-200">Loading configuration…</p>
    {:else if !grouped.length}
      <p class="text-sm text-green-200">No configurable options exposed by the server.</p>
    {:else}
      {#each grouped as group (group.group)}
        <section class="space-y-3 rounded border border-green-700/20 bg-black/30 p-3">
          <h3 class="text-xl font-semibold text-green-200">{group.group}</h3>
          <div class="space-y-3">
            {#each group.items as field (field.key)}
              <div class="space-y-1">
                <label class="block text-sm font-semibold text-green-300" for={field.key}>
                  {field.key}
                </label>
                {#if field.type === 'boolean'}
                  <label class="inline-flex items-center gap-2 text-sm text-green-200">
                    <input
                      id={field.key}
                      type="checkbox"
                      class="h-4 w-4 rounded border-green-700 bg-gray-900 text-green-500"
                      checked={values[field.key] ?? false}
                      on:change={(event) => handleChange(field, event.currentTarget.checked)}
                    />
                    {field.description}
                  </label>
                {:else}
                  <input
                    id={field.key}
                    class="w-full rounded border border-green-700 bg-gray-900 p-2 text-green-200"
                    type={field.type === 'integer' ? 'number' : 'text'}
                    value={values[field.key] ?? ''}
                    on:input={(event) => handleChange(field, event.currentTarget.value)}
                  />
                  {#if field.description}
                    <p class="text-xs text-green-300/80">{field.description}</p>
                  {/if}
                {/if}
                <p class="text-xs text-green-400/70">Default: {String(field.default ?? '')}</p>
                {#if validation[field.key]}
                  <p class="text-xs text-red-300">{validation[field.key]}</p>
                {/if}
              </div>
            {/each}
          </div>
        </section>
      {/each}
    {/if}
  {/if}
</div>
