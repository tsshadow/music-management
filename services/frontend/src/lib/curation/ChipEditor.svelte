<script>
  /**
   * A labelled list of short strings with add and remove: aliases, catalogue
   * prefixes, parent genres.
   *
   * `validate` returns null when the candidate is fine and a message when it is not,
   * so each caller keeps its own rule (a genre may not be its own parent, an alias may
   * not repeat the artist name) without this component knowing any of them.
   */
  import { Plus, X } from '@lucide/svelte';

  let {
    title,
    hint = '',
    placeholder = '',
    items = [],
    disabled = false,
    busy = false,
    validate = () => null,
    onadd,
    onremove
  } = $props();

  let draft = $state('');
  let localError = $state(null);

  function submit(event) {
    event.preventDefault();
    const candidate = draft.trim();
    const problem = validate(candidate);
    if (problem) {
      localError = problem;
      return;
    }
    localError = null;
    draft = '';
    onadd?.(candidate);
  }
</script>

<section>
  <h2 class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text m-0">{title}</h2>
  {#if hint}
    <p class="text-xs text-muma-spotify-text mt-1 mb-0">{hint}</p>
  {/if}

  <div class="flex flex-wrap gap-2 mt-3">
    {#each items as item (item)}
      <span class="flex items-center gap-2 bg-muma-spotify-light rounded-full pl-3 pr-2 py-1 text-sm">
        {item}
        {#if !disabled}
          <button
            class="bg-transparent border-none p-0 cursor-pointer text-muma-spotify-text hover:text-white flex"
            aria-label={`Verwijder ${item}`}
            onclick={() => onremove?.(item)}
          >
            <X size={14} />
          </button>
        {/if}
      </span>
    {:else}
      <span class="text-sm text-muma-spotify-text">Nog niets ingesteld.</span>
    {/each}
  </div>

  {#if !disabled}
    <form class="flex gap-2 mt-3" onsubmit={submit}>
      <input
        class="flex-1 bg-muma-spotify-light border-none rounded px-3 py-2 text-sm text-white"
        {placeholder}
        bind:value={draft}
      />
      <button
        class="flex items-center gap-1 bg-brand text-black font-bold rounded px-4 py-2 text-sm border-none cursor-pointer disabled:opacity-40"
        disabled={!draft.trim() || busy}
        type="submit"
      >
        <Plus size={16} /> Toevoegen
      </button>
    </form>
    {#if localError}
      <p class="text-xs text-red-400 mt-2 mb-0">{localError}</p>
    {/if}
  {/if}
</section>
