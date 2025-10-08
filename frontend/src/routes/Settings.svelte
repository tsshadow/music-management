<script lang="ts">
  import { onMount } from 'svelte';

  const editableFields = [
    { key: 'default_user', type: 'text', label: 'Default user' },
    { key: 'lms_source_name', type: 'text', label: 'LMS source name' },
    { key: 'api_key', type: 'text', label: 'API key' },
    { key: 'listenbrainz_user', type: 'text', label: 'ListenBrainz user' },
    { key: 'listenbrainz_token', type: 'password', label: 'ListenBrainz token' }
  ];
  let values: Record<string, string> = Object.fromEntries(editableFields.map((field) => [field.key, '']));
  let saving = false;
  let message = '';

  function handleInput(key: string, event: Event) {
    const input = event.target as HTMLInputElement;
    values = { ...values, [key]: input.value };
  }

  async function loadConfig() {
    const res = await fetch('/api/v1/config');
    if (res.ok) {
      const data = await res.json();
      values = {
        ...Object.fromEntries(editableFields.map((field) => [field.key, ''])),
        ...data.values
      };
    }
  }

  async function save() {
    saving = true;
    message = '';
    const res = await fetch('/api/v1/config', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(values)
    });
    saving = false;
    if (res.ok) {
      message = 'Saved!';
      await loadConfig();
    } else {
      message = 'Failed to save configuration';
    }
  }

  onMount(() => {
    loadConfig();
  });
</script>

<section class="settings">
  <h2>Settings</h2>
  <div class="form">
    {#each editableFields as field}
      <label>
        <span>{field.label}</span>
        <input
          type={field.type}
          value={values[field.key]}
          placeholder={`Enter ${field.label.toLowerCase()}`}
          on:input={(event) => handleInput(field.key, event)}
        />
      </label>
    {/each}
    <button on:click={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
    {#if message}
      <p class="message">{message}</p>
    {/if}
  </div>
</section>

<style>
  .settings {
    padding: 2rem;
    max-width: 640px;
    margin: 0 auto;
    background: rgba(0, 0, 0, 0.15);
    border-radius: 1rem;
  }

  .form {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  label {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  input {
    padding: 0.75rem 1rem;
    border-radius: 0.75rem;
    border: none;
    background: rgba(255, 255, 255, 0.1);
    color: var(--text-color);
  }

  button {
    align-self: flex-start;
    padding: 0.75rem 1.5rem;
    border-radius: 0.75rem;
    border: none;
    background: var(--accent-color);
    color: white;
    cursor: pointer;
  }

  .message {
    opacity: 0.8;
  }
</style>
