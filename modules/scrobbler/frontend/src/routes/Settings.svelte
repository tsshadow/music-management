<script lang="ts">
  import { onMount } from 'svelte';

  /** Settings view for application configuration and maintenance actions. */

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
  let exporting = false;
  let exportMessage = '';
  let deleting = false;
  let deleteMessage = '';
  let clearingLibrary = false;
  let libraryMessage = '';

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

  async function runExport() {
    exporting = true;
    exportMessage = '';
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (values.api_key) {
        headers['X-Api-Key'] = values.api_key;
      }
      const payload: Record<string, string> = {};
      if (values.listenbrainz_user) {
        payload.user = values.listenbrainz_user;
      }
      if (values.listenbrainz_token) {
        payload.token = values.listenbrainz_token;
      }
      const response = await fetch('/api/v1/export/listenbrainz', {
        method: 'POST',
        headers,
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const detail = await response.text();
        exportMessage = `Export failed: ${detail || response.statusText}`;
        return;
      }
      const data = await response.json();
      const exportedCount = data.exported ?? 0;
      const skippedCount = data.skipped ?? 0;
      if (skippedCount) {
        exportMessage = `Export complete: ${exportedCount} listens sent, ${skippedCount} skipped.`;
      } else {
        exportMessage = `Export complete: ${exportedCount} listens sent.`;
      }
    } catch (error) {
      exportMessage = 'Export failed: network error';
    } finally {
      exporting = false;
    }
  }

  async function deleteAllListens() {
    if (!confirm('This will permanently delete all stored listens. Are you really sure?')) {
      return;
    }
    deleting = true;
    deleteMessage = '';
    try {
      const headers: Record<string, string> = {};
      if (values.api_key) {
        headers['X-Api-Key'] = values.api_key;
      }
      const response = await fetch('/api/v1/listens', {
        method: 'DELETE',
        headers
      });
      if (!response.ok) {
        const detail = await response.text();
        deleteMessage = `Delete failed: ${detail || response.statusText}`;
        return;
      }
      deleteMessage = 'All listens deleted. You can safely run a fresh ListenBrainz import.';
    } catch (error) {
      deleteMessage = 'Delete failed: network error';
    } finally {
      deleting = false;
    }
  }

  async function deleteMediaLibrary() {
    if (!confirm('This will erase analyzer media library metadata. Continue?')) {
      return;
    }
    clearingLibrary = true;
    libraryMessage = '';
    try {
      const headers: Record<string, string> = {};
      if (values.api_key) {
        headers['X-Api-Key'] = values.api_key;
      }
      const response = await fetch('/api/v1/library', {
        method: 'DELETE',
        headers,
      });
      if (!response.ok) {
        const detail = await response.text();
        libraryMessage = `Library reset failed: ${detail || response.statusText}`;
        return;
      }
      const data = await response.json();
      const tracksRemoved = data.tracks_removed ?? 0;
      const filesRemoved = data.media_files_removed ?? 0;
      libraryMessage = `Media library cleared: ${tracksRemoved} tracks removed, ${filesRemoved} files detached.`;
    } catch (error) {
      libraryMessage = 'Library reset failed: network error';
    } finally {
      clearingLibrary = false;
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
    <div class="actions">
      <button on:click={save} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
      <button on:click={runExport} disabled={exporting} class="secondary">
        {exporting ? 'Exporting…' : 'Export to ListenBrainz'}
      </button>
      <button on:click={deleteAllListens} disabled={deleting} class="danger">
        {deleting ? 'Deleting…' : 'Delete all listens'}
      </button>
      <button on:click={deleteMediaLibrary} disabled={clearingLibrary} class="danger">
        {clearingLibrary ? 'Clearing…' : 'Delete media library data'}
      </button>
    </div>
    {#if message}
      <p class="message">{message}</p>
    {/if}
    {#if exportMessage}
      <p class="message">{exportMessage}</p>
    {/if}
    {#if deleteMessage}
      <p class="message warning">{deleteMessage}</p>
    {/if}
    {#if libraryMessage}
      <p class="message warning">{libraryMessage}</p>
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

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 1rem;
  }

  button {
    padding: 0.75rem 1.5rem;
    border-radius: 0.75rem;
    border: none;
    background: var(--accent-color);
    color: white;
    cursor: pointer;
  }

  button.secondary {
    background: rgba(255, 255, 255, 0.15);
    color: var(--text-color);
  }

  button.danger {
    background: #c43c3c;
  }

  .message {
    opacity: 0.8;
  }

  .message.warning {
    color: #f5d67b;
  }
</style>
