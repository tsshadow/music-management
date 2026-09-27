<script>
  import { t } from './i18n/index.js';

  /**
   * Picks exactly one record -- an id with a name -- from suggestions the server hands over as
   * the user types. The single-value sibling of MultiPicker.svelte, with the same field and
   * suggestion list (docs/styleguide.md, "Pickers").
   *
   * `onsearch(query)` resolves to the records to offer; `describe(record)` is an optional muted
   * second line (platform, track count, what it is linked to). Nothing typed is ever taken as
   * a choice on its own: a pick is always one of the suggestions, because what is being chosen is
   * a row the server knows, not a name.
   */
  const {
    id,
    label,
    selected = null,
    onsearch,
    onselect,
    describe = null,
    placeholder = '',
    disabled = false,
  } = $props();

  const DEBOUNCE_MS = 200;

  let query = $state('');
  let suggestions = $state([]);
  let open = $state(false);
  let searched = $state(false);
  let searchSeq = 0;

  $effect(() => {
    const needle = query.trim();
    if (!needle) {
      suggestions = [];
      searched = false;
      return;
    }
    const seq = ++searchSeq;
    const handle = setTimeout(async () => {
      try {
        const found = await onsearch(needle);
        if (seq === searchSeq) {
          suggestions = Array.isArray(found) ? found : [];
          searched = true;
        }
      } catch (error) {
        console.warn('Suggestions failed', error);
      }
    }, DEBOUNCE_MS);
    return () => clearTimeout(handle);
  });

  function pick(record) {
    onselect?.(record);
    query = '';
    suggestions = [];
    open = false;
  }

  function onkeydown(event) {
    if (event.key === 'Enter') {
      // Enter takes the only suggestion there is, and otherwise nothing: free text is no record.
      event.preventDefault();
      if (suggestions.length === 1) pick(suggestions[0]);
    } else if (event.key === 'Escape') {
      open = false;
    }
  }
</script>

<div class="flex flex-col gap-2">
  <label for={id} class="text-xs font-bold uppercase tracking-wider text-muma-spotify-text">{label}</label>
  {#if selected}
    <div class="flex items-center gap-2 bg-muma-spotify-light rounded-md px-2 py-1.5 min-h-11">
      <span class="flex items-center gap-1 bg-white/10 text-white text-sm rounded-full pl-3 pr-1 py-0.5" data-testid="{id}-selected">
        {selected.name}
        <button
          type="button"
          class="w-5 h-5 rounded-full bg-transparent border-none text-muma-spotify-text hover:text-white hover:bg-white/10 cursor-pointer flex items-center justify-center"
          aria-label={$t('common.pickAnother')}
          {disabled}
          onclick={() => onselect?.(null)}
        >×</button>
      </span>
      {#if describe}
        <span class="text-xs text-muma-spotify-text">{describe(selected)}</span>
      {/if}
    </div>
  {:else}
    <div class="relative">
      <div class="flex items-center bg-muma-spotify-light rounded-md px-2 py-1.5 min-h-11 focus-within:outline focus-within:outline-1 focus-within:outline-brand">
        <input
          {id}
          type="text"
          class="flex-1 min-w-24 bg-transparent border-none text-white text-sm outline-none placeholder:text-[#777]"
          {placeholder}
          {disabled}
          autocomplete="off"
          bind:value={query}
          onfocus={() => (open = true)}
          oninput={() => (open = true)}
          onblur={() => setTimeout(() => (open = false), 150)}
          {onkeydown}
          role="combobox"
          aria-expanded={open && suggestions.length > 0}
          aria-controls="{id}-suggestions"
          aria-autocomplete="list"
        />
      </div>
      {#if open && query.trim() && searched}
        <ul
          id="{id}-suggestions"
          role="listbox"
          class="absolute left-0 right-0 top-full mt-1 bg-muma-spotify-light rounded-md shadow-xl border border-white/5 py-1 z-30 max-h-64 overflow-y-auto list-none m-0 p-0"
        >
          {#each suggestions as record (record.id)}
            <li role="option" aria-selected="false">
              <button
                type="button"
                class="w-full text-left px-3 py-1.5 text-sm text-white hover:bg-white/10 bg-transparent border-none cursor-pointer"
                onmousedown={(event) => event.preventDefault()}
                onclick={() => pick(record)}
              >
                {record.name}
                {#if describe}
                  <span class="block text-xs text-muma-spotify-text">{describe(record)}</span>
                {/if}
              </button>
            </li>
          {:else}
            <li class="px-3 py-1.5 text-sm text-muma-spotify-text">{$t('common.noResults')}</li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</div>
