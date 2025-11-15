<script lang="ts">
  import { onMount } from 'svelte';
  import { importerApi } from '$lib/api';

  /** Form editor for importer configuration grouped by logical sections. */

  const configEndpoint = importerApi.url('/config');

  type ConfigField = {
    key: string;
    type: 'string' | 'boolean' | 'integer';
    group: string;
    description: string;
    nullable: boolean;
    default: unknown;
    value: unknown;
  };

  type Message = { kind: 'success' | 'error'; text: string } | null;

  let fields: ConfigField[] = [];
  let values: Record<string, unknown> = {};
  let initialValues: Record<string, unknown> = {};
  let errors: Record<string, string | null> = {};
  let loading = true;
  let saving = false;
  let message: Message = null;

  onMount(async () => {
    await loadConfig();
  });

  async function loadConfig() {
    loading = true;
    message = null;
    try {
      const response = await fetch(configEndpoint);
      if (!response.ok) {
        throw new Error(`Failed to load configuration: ${response.status}`);
      }
      const data = await response.json();
      fields = data.fields ?? [];
      const nextValues: Record<string, unknown> = {};
      const nextErrors: Record<string, string | null> = {};
      for (const field of fields) {
        nextValues[field.key] = normalize(field, field.value);
        nextErrors[field.key] = null;
      }
      values = nextValues;
      initialValues = { ...nextValues };
      errors = nextErrors;
    } catch (err) {
      console.error(err);
      message = { kind: 'error', text: err instanceof Error ? err.message : 'Failed to load configuration' };
    } finally {
      loading = false;
    }
  }

  function normalize(field: ConfigField, value: unknown) {
    if (value === undefined) {
      return field.type === 'boolean' ? false : null;
    }
    if (field.type === 'integer') {
      if (value === '' || value === null) {
        return null;
      }
      if (typeof value === 'number') {
        return Number.isFinite(value) ? value : null;
      }
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : null;
    }
    if (field.type === 'boolean') {
      if (typeof value === 'boolean') return value;
      if (typeof value === 'string') return ['1', 'true', 'yes', 'on'].includes(value.toLowerCase());
      if (typeof value === 'number') return value !== 0;
      return false;
    }
    return typeof value === 'string' ? value : value ?? '';
  }

  $: groups = groupFields(fields);
  $: hasErrors = Object.values(errors).some((value) => Boolean(value));
  $: hasChanges = fields.some((field) => !isEqual(values[field.key], initialValues[field.key]));

  function groupFields(list: ConfigField[]) {
    const map = new Map<string, ConfigField[]>();
    for (const field of list) {
      const group = field.group ?? 'General';
      if (!map.has(group)) {
        map.set(group, []);
      }
      map.get(group)?.push(field);
    }
    return Array.from(map.entries()).map(([group, groupFields]) => ({ group, fields: groupFields }));
  }

  function isEqual(a: unknown, b: unknown) {
    if (a === b) return true;
    if (a == null && b == null) return true;
    if (typeof a === 'number' && typeof b === 'number') {
      return Number.isNaN(a) && Number.isNaN(b) ? true : a === b;
    }
    if (typeof a === 'string' && typeof b === 'string') {
      return a === b;
    }
    return JSON.stringify(a) === JSON.stringify(b);
  }

  function onStringChange(field: ConfigField, event: Event) {
    const target = event.target as HTMLInputElement;
    values = { ...values, [field.key]: target.value };
  }

  function onBooleanChange(field: ConfigField, event: Event) {
    const target = event.target as HTMLInputElement;
    values = { ...values, [field.key]: target.checked };
  }

  function onIntegerChange(field: ConfigField, event: Event) {
    const target = event.target as HTMLInputElement;
    const raw = target.value.trim();
    if (raw === '') {
      values = { ...values, [field.key]: null };
      errors = { ...errors, [field.key]: field.nullable ? null : 'Value required' };
      return;
    }
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) {
      errors = { ...errors, [field.key]: 'Enter a valid number' };
      return;
    }
    errors = { ...errors, [field.key]: null };
    values = { ...values, [field.key]: parsed };
  }

  async function saveChanges() {
    if (!hasChanges || hasErrors || saving) {
      return;
    }
    const updates: Record<string, unknown> = {};
    for (const field of fields) {
      const current = values[field.key];
      const initial = initialValues[field.key];
      if (!isEqual(current, initial)) {
        updates[field.key] = current;
      }
    }
    if (Object.keys(updates).length === 0) {
      return;
    }
    saving = true;
    message = null;
    try {
      const response = await fetch(configEndpoint, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates })
      });
      if (!response.ok) {
        const errorBody = await safeJson(response);
        const detail = errorBody?.detail ?? response.statusText;
        throw new Error(Array.isArray(detail) ? detail.join(', ') : String(detail));
      }
      const body = await response.json();
      const saved = body.values ?? {};
      const nextInitial = { ...initialValues };
      for (const [key, value] of Object.entries(saved)) {
        nextInitial[key] = normalize(fields.find((field) => field.key === key)!, value);
      }
      initialValues = nextInitial;
      values = { ...values, ...nextInitial };
      message = { kind: 'success', text: 'Configuration saved successfully.' };
    } catch (err) {
      console.error(err);
      message = { kind: 'error', text: err instanceof Error ? err.message : 'Failed to save configuration' };
    } finally {
      saving = false;
    }
  }

  async function safeJson(response: Response) {
    try {
      return await response.json();
    } catch (error) {
      return null;
    }
  }
</script>

<div class="space-y-6 rounded border border-green-700/40 bg-black/60 p-6">
  <div class="flex items-center justify-between">
    <h2 class="text-2xl font-semibold text-green-300">Configuration</h2>
    <div class="space-x-2">
      <button
        class="rounded border border-green-500 px-3 py-1 text-sm text-green-300 hover:bg-green-500/10 disabled:cursor-not-allowed disabled:opacity-40"
        on:click={loadConfig}
        disabled={loading || saving}
      >
        Refresh
      </button>
      <button
        class="rounded bg-green-600 px-4 py-1 font-semibold text-black shadow hover:bg-green-500 disabled:cursor-not-allowed disabled:opacity-40"
        on:click={saveChanges}
        disabled={loading || saving || hasErrors || !hasChanges}
      >
        {saving ? 'Saving…' : 'Save changes'}
      </button>
    </div>
  </div>

  {#if loading}
    <p class="text-sm text-green-200">Loading configuration…</p>
  {:else}
    {#if message}
      <div
        class={`rounded border px-3 py-2 text-sm ${
          message.kind === 'success'
            ? 'border-green-500 bg-green-500/10 text-green-100'
            : 'border-red-500 bg-red-500/10 text-red-200'
        }`}
      >
        {message.text}
      </div>
    {/if}

    <div class="space-y-6">
      {#each groups as group}
        <section class="space-y-4">
          <h3 class="text-lg font-semibold text-green-200">{group.group}</h3>
          <div class="grid gap-4 md:grid-cols-2">
            {#each group.fields as field}
              <label class="flex flex-col rounded border border-green-700/40 bg-gray-900/70 p-3 text-sm text-green-100">
                <span class="mb-2 font-semibold text-green-300">{field.key}</span>
                {#if field.type === 'boolean'}
                  <label class="inline-flex items-center gap-2 text-green-200">
                    <input
                      class="h-4 w-4 rounded border-green-700 bg-gray-900 text-green-500"
                      type="checkbox"
                      checked={Boolean(values[field.key])}
                      on:change={(event) => onBooleanChange(field, event)}
                    />
                    <span>{field.description || 'Toggle value'}</span>
                  </label>
                {:else if field.type === 'integer'}
                  <input
                    class="rounded border border-green-700 bg-gray-950 p-2 text-green-200 focus:border-green-500 focus:outline-none"
                    type="number"
                    value={values[field.key] ?? ''}
                    on:input={(event) => onIntegerChange(field, event)}
                    placeholder={field.nullable ? 'Optional' : 'Required number'}
                  />
                  <p class="mt-2 text-xs text-green-300/80">{field.description}</p>
                {:else}
                  <input
                    class="rounded border border-green-700 bg-gray-950 p-2 text-green-200 focus:border-green-500 focus:outline-none"
                    type="text"
                    value={typeof values[field.key] === 'string' ? (values[field.key] as string) : ''}
                    on:input={(event) => onStringChange(field, event)}
                    placeholder={field.nullable ? 'Optional' : 'Required'}
                  />
                  <p class="mt-2 text-xs text-green-300/80">{field.description}</p>
                {/if}
                {#if errors[field.key]}
                  <span class="mt-2 text-xs text-red-300">{errors[field.key]}</span>
                {/if}
              </label>
            {/each}
          </div>
        </section>
      {/each}
    </div>
  {/if}
</div>
