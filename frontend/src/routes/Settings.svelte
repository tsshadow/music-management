<script lang="ts">
  import { onMount } from 'svelte';

  const editableKeys = ['default_user', 'lms_source_name', 'api_key'];
  let values: Record<string, string> = {
    default_user: '',
    lms_source_name: '',
    api_key: ''
  };
  let saving = false;
  let message = '';

  async function loadConfig() {
    const res = await fetch('/api/v1/config');
    if (res.ok) {
      const data = await res.json();
      values = { ...data.values };
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
    {#each editableKeys as key}
      <label>
        <span>{key}</span>
        <input
          type="text"
          bind:value={values[key]}
          placeholder={`Enter ${key}`}
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
