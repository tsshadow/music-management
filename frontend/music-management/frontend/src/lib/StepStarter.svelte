<script>
import { createEventDispatcher, onDestroy } from 'svelte';
import { getJobsContext } from '$lib/jobs-context';

const { steps, start, accounts } = getJobsContext();
let selected = '';
let repeat = false;
let repeatInterval = 0;
let breakOnExisting = false;
let redownload = false;
let youtubeUrl = '';
let availableAccounts = [];
let selectedAccount = '';
let accountType = '';
let accountOptions = { soundcloud: [], youtube: [] };
let selectedAccounts = { soundcloud: '', youtube: '' };
const breakOnExistingSteps = ['download', 'download-soundcloud', 'download-youtube'];
const redownloadSteps = ['download', 'download-soundcloud', 'download-youtube'];
const accountStepMap = {
  'download-soundcloud': 'soundcloud',
  'download-youtube': 'youtube',
};
const dispatch = createEventDispatcher();

const unsubscribeAccounts = accounts.subscribe(value => {
  accountOptions = value ?? { soundcloud: [], youtube: [] };
});

onDestroy(() => {
  unsubscribeAccounts();
});

$: if (!selected && $steps.length > 0) {
  selected = $steps[0];
}

$: if (!breakOnExistingSteps.includes(selected)) {
  breakOnExisting = false;
}

$: if (!redownloadSteps.includes(selected)) {
  redownload = false;
}

$: accountType = accountStepMap[selected] ?? '';
$: availableAccounts = accountType ? accountOptions[accountType] ?? [] : [];
$: selectedAccount = accountType ? selectedAccounts[accountType] ?? '' : '';
$: if (accountType && selectedAccount && !availableAccounts.includes(selectedAccount)) {
  selectedAccount = '';
  selectedAccounts = { ...selectedAccounts, [accountType]: '' };
}

function onAccountChange(event) {
  const value = event.target.value;
  if (accountType) {
    selectedAccounts = { ...selectedAccounts, [accountType]: value };
    selectedAccount = value;
  }
}

async function startSelected() {
  if (!selected) return;
  const options = {};
  if (repeat) {
    options.repeat = true;
    if (repeatInterval > 0) options.interval = repeatInterval;
  }
  if (breakOnExisting && breakOnExistingSteps.includes(selected))
    options.breakOnExisting = true;
  if (redownload && redownloadSteps.includes(selected)) options.redownload = true;
  if (selected === 'manual-youtube' && youtubeUrl) options.url = youtubeUrl;
  if (accountType && selectedAccount) {
    options.account = selectedAccount;
  }
  const job = await start(selected, options);
  if (job) {
    dispatch('started', job);
  }
}
</script>

<div class="space-y-4 rounded border border-green-700/40 bg-black/60 p-4">
  <select
    class="rounded border border-green-700 bg-gray-900 p-2 text-green-400"
    bind:value={selected}
  >
    {#each $steps as step}
      <option value={step}>{step}</option>
    {/each}
  </select>
  <label class="ml-2 inline-flex items-center gap-2 text-sm">
    <input
      class="h-4 w-4 rounded border-green-700 bg-gray-900 text-green-500"
      type="checkbox"
      bind:checked={repeat}
    />
    Repeat
  </label>
  <input
    class="rounded border border-green-700 bg-gray-900 p-2 text-green-400 disabled:opacity-50"
    type="number"
    min="0"
    placeholder="Repeat interval"
    bind:value={repeatInterval}
    disabled={!repeat}
  />
  {#if breakOnExistingSteps.includes(selected)}
    <label class="ml-2 inline-flex items-center gap-2 text-sm">
      <input
        class="h-4 w-4 rounded border-green-700 bg-gray-900 text-green-500"
        type="checkbox"
        bind:checked={breakOnExisting}
      />
      Break on existing
    </label>
  {/if}
  {#if redownloadSteps.includes(selected)}
    <label class="ml-2 inline-flex items-center gap-2 text-sm">
      <input
        class="h-4 w-4 rounded border-green-700 bg-gray-900 text-green-500"
        type="checkbox"
        bind:checked={redownload}
      />
      Redownload (ignore archive)
    </label>
  {/if}
  {#if selected === 'manual-youtube'}
    <input
      class="rounded border border-green-700 bg-gray-900 p-2 text-green-400"
      type="text"
      placeholder="YouTube URL"
      bind:value={youtubeUrl}
    />
  {/if}
  {#if accountType}
    <label class="block text-sm">
      <span class="mb-1 block text-green-300">Account</span>
      <select
        class="w-full rounded border border-green-700 bg-gray-900 p-2 text-green-400"
        bind:value={selectedAccount}
        on:change={onAccountChange}
      >
        <option value="">All accounts</option>
        {#each availableAccounts as account}
          <option value={account}>{account}</option>
        {/each}
      </select>
    </label>
  {/if}
  <button
    class="rounded bg-green-600 px-4 py-2 font-bold text-black shadow hover:bg-green-500"
    on:click={startSelected}
  >
    Start
  </button>
</div>
