<script>
  import { t, format } from '../../i18n/index.js';
  import { onMount } from 'svelte';
  import { 
    RefreshCw, 
    UserPlus, 
    CheckCircle, 
    XCircle, 
    Clock, 
    ShieldCheck, 
    ShieldAlert,
    User
  } from '@lucide/svelte';
  import { hasPermission } from '../../store.js';

  let { API_BASE, getHeaders, onMessage, onError, users = [] } = $props();

  let requests = $state([]);
  let loading = $state(false);
  let statusFilter = $state('pending'); // 'pending', 'approved', 'rejected'
  let confirmingAction = $state(null); // { type: 'approve'|'reject'|'unapprove', request: object }
  let linkUserId = $state(''); // when approving: existing user to link the Google identity to, instead of creating a new account
  let approveDisplayName = $state(''); // optional override for the display name shown for the (new or linked) account

  async function fetchRequests() {
    loading = true;
    try {
      const res = await fetch(`${API_BASE}/api/user-requests?status=${statusFilter}`, {
        headers: getHeaders()
      });
      if (res.ok) {
        requests = await res.json();
      } else {
        onError($t('management.requests.loadFailed'));
      }
    } catch {
      onError($t('management.requests.loadNetworkError'));
    } finally {
      loading = false;
    }
  }

  async function approveRequest(request) {
    try {
      const res = await fetch(`${API_BASE}/api/user-requests/${request.id}/approve`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({
          link_user_id: linkUserId ? parseInt(linkUserId) : null,
          display_name: approveDisplayName || null
        })
      });
      if (res.ok) {
        onMessage(
          linkUserId
            ? $t('management.requests.linkedMessage', { name: request.display_name })
            : $t('management.requests.approvedMessage', { name: request.display_name })
        );
        confirmingAction = null;
        linkUserId = '';
        approveDisplayName = '';
        fetchRequests();
      } else {
        const data = await res.json();
        onError(data.detail || $t('management.requests.approveFailed'));
      }
    } catch {
      onError($t('management.requests.networkError'));
    }
  }

  async function unapproveRequest(request) {
    try {
      const res = await fetch(`${API_BASE}/api/user-requests/${request.id}/unapprove`, {
        method: 'POST',
        headers: getHeaders({ 'Content-Type': 'application/json' }),
        body: JSON.stringify({})
      });
      if (res.ok) {
        onMessage($t('management.requests.undoneMessage', { name: request.display_name }));
        confirmingAction = null;
        fetchRequests();
      } else {
        const data = await res.json();
        onError(data.detail || $t('management.requests.undoFailed'));
      }
    } catch {
      onError($t('management.requests.networkError'));
    }
  }

  async function rejectRequest(request) {
    try {
      const res = await fetch(`${API_BASE}/api/user-requests/${request.id}/reject`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage($t('management.requests.rejectedMessage', { name: request.display_name }));
        confirmingAction = null;
        fetchRequests();
      } else {
        const data = await res.json();
        onError(data.detail || $t('management.requests.rejectFailed'));
      }
    } catch {
      onError($t('management.requests.networkError'));
    }
  }

  $effect(() => {
    if (statusFilter) {
      fetchRequests();
    }
  });

  onMount(fetchRequests);
</script>

<section class="space-y-8 animate-in slide-in-from-bottom-4 duration-500">
  <header class="flex justify-between items-end">
    <div>
      <h2 class="text-4xl font-extrabold mb-2">🛡️ {$t('management.tabs.userRequests')}</h2>
      <p class="text-muma-spotify-text">{$t('management.requests.subtitle')}</p>
    </div>
    
    <div class="flex bg-muma-spotify-panel p-1 rounded-full border border-white/5">
      <button 
        class="px-4 py-1.5 rounded-full text-xs font-bold transition-colors {statusFilter === 'pending' ? 'bg-white text-black' : 'text-muma-spotify-text hover:text-white'}"
        onclick={() => statusFilter = 'pending'}
      >
        {$t('management.requests.pending')}
      </button>
      <button 
        class="px-4 py-1.5 rounded-full text-xs font-bold transition-colors {statusFilter === 'approved' ? 'bg-white text-black' : 'text-muma-spotify-text hover:text-white'}"
        onclick={() => statusFilter = 'approved'}
      >
        {$t('management.requests.approved')}
      </button>
      <button 
        class="px-4 py-1.5 rounded-full text-xs font-bold transition-colors {statusFilter === 'rejected' ? 'bg-white text-black' : 'text-muma-spotify-text hover:text-white'}"
        onclick={() => statusFilter = 'rejected'}
      >
        {$t('management.requests.rejected')}
      </button>
    </div>
  </header>

  <div class="bg-muma-spotify-panel/40 rounded-xl border border-white/5 overflow-hidden">
    <div class="p-6 bg-black/20 flex justify-between items-center">
      <h3 class="text-xl font-bold flex items-center gap-2">
        {#if statusFilter === 'pending'}<Clock size={20} class="text-yellow-500" />{/if}
        {#if statusFilter === 'approved'}<ShieldCheck size={20} class="text-brand" />{/if}
        {#if statusFilter === 'rejected'}<ShieldAlert size={20} class="text-red-500" />{/if}
        {statusFilter === 'pending' ? $t('management.requests.pendingHeading') : statusFilter === 'approved' ? $t('management.requests.approvedHeading') : $t('management.requests.rejectedHeading')}
      </h3>
      <button 
        onclick={fetchRequests} 
        disabled={loading}
        class="text-muma-spotify-text hover:text-white transition-colors disabled:opacity-50"
      >
        <RefreshCw size={18} class={loading ? 'animate-spin' : ''} />
      </button>
    </div>

    <div class="min-h-[200px]">
      {#if loading && requests.length === 0}
        <div class="flex items-center justify-center p-20">
          <RefreshCw class="animate-spin text-brand" size={32} />
        </div>
      {:else if requests.length === 0}
        <div class="flex flex-col items-center justify-center p-20 text-muma-spotify-text">
          <UserPlus size={48} class="mb-4 opacity-20" />
          <p>{$t('management.requests.emptyForStatus', { status: statusFilter })}</p>
        </div>
      {:else}
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead>
              <tr class="bg-white/5 text-muma-spotify-text text-[10px] uppercase tracking-wider">
                <th class="p-4">{$t('management.scrobble.user')}</th>
                <th class="p-4">{$t('management.requests.requestedAt')}</th>
                {#if statusFilter !== 'pending'}
                  <th class="p-4">{$t('management.requests.reviewedBy')}</th>
                  <th class="p-4">{$t('management.requests.reviewedAt')}</th>
                {/if}
                {#if statusFilter === 'pending' || statusFilter === 'approved'}
                  <th class="p-4 text-right">{$t('management.genres.actions')}</th>
                {/if}
              </tr>
            </thead>
            <tbody class="divide-y divide-muma-spotify-panel/30">
              {#each requests as request (request.id)}
                <tr class="hover:bg-white/5 transition-colors">
                  <td class="p-4">
                    <div class="flex items-center gap-3">
                      {#if request.avatar_url}
                        <img src={request.avatar_url} alt="" class="w-10 h-10 rounded-full" />
                      {:else}
                        <div class="w-10 h-10 bg-white/10 rounded-full flex items-center justify-center">
                          <User size={20} class="text-muma-spotify-text" />
                        </div>
                      {/if}
                      <div>
                        <div class="font-bold">{request.display_name}</div>
                        <div class="text-xs text-muma-spotify-text">{request.email}</div>
                      </div>
                    </div>
                  </td>
                  <td class="p-4 text-muma-spotify-text">
                    {$format.dateTime(request.requested_at)}
                  </td>
                  {#if statusFilter !== 'pending'}
                    <td class="p-4">
                      <span class="text-xs bg-white/5 px-2 py-1 rounded">
                        {request.reviewed_by_user_id || $t('management.requests.system')}
                      </span>
                    </td>
                    <td class="p-4 text-muma-spotify-text">
                      {request.reviewed_at ? $format.dateTime(request.reviewed_at) : '—'}
                    </td>
                  {/if}
                  {#if statusFilter === 'pending'}
                    <td class="p-4 text-right">
                      <div class="flex justify-end gap-2">
                        {#if hasPermission('user-requests.approve')}
                          <button 
                            onclick={() => { linkUserId = ''; approveDisplayName = ''; confirmingAction = { type: 'approve', request }; }}
                            class="bg-brand text-black px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                          >
                            <CheckCircle size={14} /> {$t('management.genres.approve')}
                          </button>
                        {/if}
                        {#if hasPermission('user-requests.reject')}
                          <button 
                            onclick={() => confirmingAction = { type: 'reject', request }}
                            class="bg-red-500/10 text-red-500 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                          >
                            <XCircle size={14} /> {$t('management.requests.reject')}
                          </button>
                        {/if}
                      </div>
                    </td>
                  {/if}
                  {#if statusFilter === 'approved'}
                    <td class="p-4 text-right">
                      {#if hasPermission('user-requests.unapprove')}
                        <button 
                          onclick={() => confirmingAction = { type: 'unapprove', request }}
                          class="bg-red-500/10 text-red-500 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1 ml-auto"
                        >
                          <XCircle size={14} /> {$t('management.requests.undo')}
                        </button>
                      {/if}
                    </td>
                  {/if}
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
    </div>
  </div>
</section>

{#if confirmingAction}
<div class="fixed inset-0 bg-black/80 flex items-center justify-center z-[1100] animate-in fade-in duration-200">
  <div class="bg-muma-spotify-light p-8 rounded-xl border border-white/10 max-w-md w-full shadow-2xl">
    <h3 class="text-2xl font-bold mb-4 flex items-center gap-2">
      {#if confirmingAction.type === 'approve'}
        <CheckCircle class="text-brand" /> {$t('management.requests.confirmApprove')}
      {:else if confirmingAction.type === 'unapprove'}
        <ShieldAlert class="text-red-500" /> {$t('management.requests.confirmUndo')}
      {:else}
        <ShieldAlert class="text-red-500" /> {$t('management.requests.confirmReject')}
      {/if}
    </h3>
    <p class="text-muma-spotify-text mb-6">
      {#if confirmingAction.type === 'approve'}
        {@const [before, after] = $t('management.requests.approveQuestion').split('{name}')}
        {before}<b>{confirmingAction.request.display_name}</b>{after}
        {#if linkUserId}
          {$t('management.requests.approveLinkHelp')}
        {:else}
          {$t('management.requests.approveCreateHelp')}
        {/if}
      {:else if confirmingAction.type === 'unapprove'}
        {@const [before, after] = $t('management.requests.undoQuestion').split('{name}')}
        {before}<b>{confirmingAction.request.display_name}</b>{after}
        {#if confirmingAction.request.linked_existing}
          {$t('management.requests.undoLinkHelp')}
        {:else}
          {$t('management.requests.undoCreateHelp')}
        {/if}
      {:else}
        {@const [before, after] = $t('management.requests.rejectQuestion').split('{name}')}
        {before}<b>{confirmingAction.request.display_name}</b>{after}
      {/if}
    </p>
    {#if confirmingAction.type === 'approve'}
      <div class="mb-6">
        <label for="approve-display-name" class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">
          {$t('management.requests.displayName')}
        </label>
        <input
          id="approve-display-name"
          type="text"
          bind:value={approveDisplayName}
          placeholder={confirmingAction.request.display_name}
          class="w-full bg-muma-spotify-panel/30 border border-muma-spotify-panel rounded-md p-2 focus:outline-none focus:border-brand transition-colors text-sm text-white"
        />
      </div>
    {/if}
    {#if confirmingAction.type === 'approve' && users.length > 0}
      <div class="mb-6">
        <label for="link-user" class="block text-xs font-bold text-muma-spotify-text uppercase mb-1">
          {$t('management.requests.samePerson')}
        </label>
        <select
          id="link-user"
          bind:value={linkUserId}
          class="w-full bg-muma-spotify-panel/30 border border-muma-spotify-panel rounded-md p-2 focus:outline-none focus:border-brand transition-colors text-sm text-white"
        >
          <option value="">{$t('management.requests.createNew')}</option>
          {#each users as user (user.id)}
            <option value={user.id}>{$t('management.requests.linkTo', { name: user.display_name ? `${user.username} (${user.display_name})` : user.username })}</option>
          {/each}
        </select>
      </div>
    {/if}
    <div class="flex gap-4">
      <button 
        class="flex-1 py-3 rounded-full font-bold transition-all {confirmingAction.type === 'approve' ? 'bg-brand text-black hover:scale-105' : 'bg-red-600 text-white hover:bg-red-700'}"
        onclick={() => {
          if (confirmingAction.type === 'approve') approveRequest(confirmingAction.request);
          else if (confirmingAction.type === 'unapprove') unapproveRequest(confirmingAction.request);
          else rejectRequest(confirmingAction.request);
        }}
      >
        {#if confirmingAction.type === 'approve'}{$t('management.requests.confirmApproveButton')}{:else if confirmingAction.type === 'unapprove'}{$t('management.requests.confirmUndoButton')}{:else}{$t('management.requests.confirmRejectButton')}{/if}
      </button>
      <button 
        class="flex-1 py-3 rounded-full font-bold bg-white/10 text-white hover:bg-white/20 transition-all"
        onclick={() => confirmingAction = null}
      >
        {$t('common.cancel')}
      </button>
    </div>
  </div>
</div>
{/if}
