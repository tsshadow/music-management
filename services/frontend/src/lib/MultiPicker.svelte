<script>
  import { t } from './i18n/index.js';

  /**
   * A row of chips plus a box to add one more: the way the preset builder collects several
   * genres, artists, labels, festivals or years for one query.
   *
   * `options` is the whole list when the server can hand it over in one go (genres, labels,
   * years, festivals); `onsearch` is for a list too long for that (artists), and is asked for
   * suggestions as the listener types. Enter adds whatever is typed even when it matches no
   * suggestion -- the server's cluster names are free text, and a name a listener knows is a
   * better guess than nothing. Each chip's × takes it out again.
   */
  const {
    id,
    label,
    selected = [],
    options = [],
    onsearch = null,
    placeholder = '',
    onchange,
  } = $props();

  const MAX_SUGGESTIONS = 12;

  let query = $state('');
  let remote = $state([]);
  let open = $state(false);
  let searchSeq = 0;

  const suggestions = $derived.by(() => {
    const needle = query.trim().toLowerCase();
    const pool = onsearch ? remote : options;
    return pool
      .map((option) => (typeof option === 'string' ? option : option?.value ?? option?.name ?? ''))
      .filter((name) => name && !selected.includes(name))
      .filter((name) => !needle || name.toLowerCase().includes(needle))
      .slice(0, MAX_SUGGESTIONS);
  });

  $effect(() => {
    const needle = query.trim();
    if (!onsearch) return;
    if (!needle) {
      remote = [];
      return;
    }
    const seq = ++searchSeq;
    const handle = setTimeout(async () => {
      try {
        const found = await onsearch(needle);
        if (seq === searchSeq) remote = Array.isArray(found) ? found : [];
      } catch (error) {
        console.warn('Suggestions failed', error);
      }
    }, 200);
    return () => clearTimeout(handle);
  });

  function add(value) {
    const name = String(value ?? '').trim();
    if (!name || selected.includes(name)) return;
    onchange?.([...selected, name]);
    query = '';
    open = false;
  }

  function remove(name) {
    onchange?.(selected.filter((item) => item !== name));
  }

  function onkeydown(event) {
    if (event.key === 'Enter') {
      event.preventDefault();
      add(suggestions.length === 1 ? suggestions[0] : query);
    } else if (event.key === 'Backspace' && !query && selected.length) {
      remove(selected[selected.length - 1]);
    } else if (event.key === 'Escape') {
      open = false;
    }
  }
</script>

<div class="flex flex-col gap-2">
  <label for={id} class="text-xs font-bold uppercase tracking-wider text-[#b3b3b3]">{label}</label>
  <div class="relative">
    <div class="flex flex-wrap items-center gap-2 bg-[#282828] rounded-md px-2 py-1.5 min-h-11 focus-within:outline focus-within:outline-1 focus-within:outline-brand">
      {#each selected as name (name)}
        <span class="flex items-center gap-1 bg-white/10 text-white text-sm rounded-full pl-3 pr-1 py-0.5">
          {name}
          <button
            type="button"
            class="w-5 h-5 rounded-full bg-transparent border-none text-[#b3b3b3] hover:text-white hover:bg-white/10 cursor-pointer flex items-center justify-center"
            aria-label={$t('presetBuilder.remove', { name })}
            onclick={() => remove(name)}
          >×</button>
        </span>
      {/each}
      <input
        {id}
        type="text"
        class="flex-1 min-w-24 bg-transparent border-none text-white text-sm outline-none placeholder:text-[#777]"
        {placeholder}
        autocomplete="off"
        bind:value={query}
        onfocus={() => (open = true)}
        onblur={() => setTimeout(() => (open = false), 150)}
        onkeydown={onkeydown}
        role="combobox"
        aria-expanded={open && suggestions.length > 0}
        aria-controls="{id}-suggestions"
        aria-autocomplete="list"
      />
    </div>
    {#if open && suggestions.length > 0}
      <ul
        id="{id}-suggestions"
        role="listbox"
        class="absolute left-0 right-0 top-full mt-1 bg-[#282828] rounded-md shadow-xl border border-white/5 py-1 z-30 max-h-64 overflow-y-auto list-none m-0 p-0"
      >
        {#each suggestions as name (name)}
          <li role="option" aria-selected="false">
            <button
              type="button"
              class="w-full text-left px-3 py-1.5 text-sm text-white hover:bg-white/10 bg-transparent border-none cursor-pointer"
              onmousedown={(event) => event.preventDefault()}
              onclick={() => add(name)}
            >{name}</button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>
</div>
