<script>
  import { visibleSortOptions, allSortOptions } from '../store.js';

  /**
   * Toggles the visibility of a specific sort option for a given type.
   *
   * @param {string} type - The content type (songs, albums, or artists).
   * @param {string} id - The sort option identifier.
   */
  function toggleOption(type, id) {
    visibleSortOptions.update(options => {
      const current = options[type];
      if (current.includes(id)) {
        options[type] = current.filter(i => i !== id);
      } else {
        options[type] = [...current, id];
      }
      return options;
    });
  }
</script>

<section class="max-w-3xl">
  <h3 class="text-2xl font-bold mb-2">Geavanceerde Opties</h3>
  <p class="text-[#b3b3b3] mb-8">Kies welke sorteeropties zichtbaar moeten zijn in de interface.</p>

  <div class="flex flex-col gap-8">
    {#each Object.entries(allSortOptions) as [type, options]}
      <div>
        <h4 class="text-sm font-bold text-[#b3b3b3] uppercase tracking-wider mb-4">
          {type === 'songs' ? 'Nummers' : type === 'albums' ? 'Albums' : 'Artiesten'}
        </h4>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
          {#each options as option}
            <label class="flex items-center gap-3 p-3 bg-[#181818] rounded-md border border-transparent hover:border-[#3e3e3e] cursor-pointer transition-colors">
              <input
                type="checkbox"
                class="w-5 h-5 accent-brand"
                checked={$visibleSortOptions[type].includes(option.id)}
                onchange={() => toggleOption(type, option.id)}
              />
              <span class="text-white font-medium">{option.label}</span>
            </label>
          {/each}
        </div>
      </div>
    {/each}
  </div>
</section>
