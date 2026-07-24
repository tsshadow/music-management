<script>
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

  let { API_BASE, getHeaders, onMessage, onError } = $props();

  let requests = $state([]);
  let loading = $state(false);
  let statusFilter = $state('pending'); // 'pending', 'approved', 'rejected'
  let confirmingAction = $state(null); // { type: 'approve'|'reject', request: object }

  async function fetchRequests() {
    loading = true;
    try {
      const res = await fetch(`${API_BASE}/api/user-requests?status=${statusFilter}`, {
        headers: getHeaders()
      });
      if (res.ok) {
        requests = await res.json();
      } else {
        onError("Kon toegangsverzoeken niet ophalen.");
      }
    } catch (err) {
      onError("Netwerkfout bij ophalen verzoeken.");
    } finally {
      loading = false;
    }
  }

  async function approveRequest(request) {
    try {
      const res = await fetch(`${API_BASE}/api/user-requests/${request.id}/approve`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage(`Verzoek van ${request.display_name} goedgekeurd!`);
        confirmingAction = null;
        fetchRequests();
      } else {
        const data = await res.json();
        onError(data.detail || "Goedkeuren mislukt.");
      }
    } catch (err) {
      onError("Netwerkfout.");
    }
  }

  async function rejectRequest(request) {
    try {
      const res = await fetch(`${API_BASE}/api/user-requests/${request.id}/reject`, {
        method: 'POST',
        headers: getHeaders()
      });
      if (res.ok) {
        onMessage(`Verzoek van ${request.display_name} afgewezen.`);
        confirmingAction = null;
        fetchRequests();
      } else {
        const data = await res.json();
        onError(data.detail || "Afwijzen mislukt.");
      }
    } catch (err) {
      onError("Netwerkfout.");
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
      <h2 class="text-4xl font-extrabold mb-2">🛡️ Toegangsverzoeken</h2>
      <p class="text-spotify-lightgray">Beheer aanvragen van nieuwe gebruikers via Google Login.</p>
    </div>
    
    <div class="flex bg-spotify-gray p-1 rounded-full border border-white border-opacity-5">
      <button 
        class="px-4 py-1.5 rounded-full text-xs font-bold transition-colors {statusFilter === 'pending' ? 'bg-white text-black' : 'text-spotify-lightgray hover:text-white'}"
        onclick={() => statusFilter = 'pending'}
      >
        Wachtend
      </button>
      <button 
        class="px-4 py-1.5 rounded-full text-xs font-bold transition-colors {statusFilter === 'approved' ? 'bg-white text-black' : 'text-spotify-lightgray hover:text-white'}"
        onclick={() => statusFilter = 'approved'}
      >
        Goedgekeurd
      </button>
      <button 
        class="px-4 py-1.5 rounded-full text-xs font-bold transition-colors {statusFilter === 'rejected' ? 'bg-white text-black' : 'text-spotify-lightgray hover:text-white'}"
        onclick={() => statusFilter = 'rejected'}
      >
        Afgewezen
      </button>
    </div>
  </header>

  <div class="bg-spotify-gray bg-opacity-40 rounded-xl border border-white border-opacity-5 overflow-hidden">
    <div class="p-6 bg-black bg-opacity-20 flex justify-between items-center">
      <h3 class="text-xl font-bold flex items-center gap-2">
        {#if statusFilter === 'pending'}<Clock size={20} class="text-yellow-500" />{/if}
        {#if statusFilter === 'approved'}<ShieldCheck size={20} class="text-spotify-green" />{/if}
        {#if statusFilter === 'rejected'}<ShieldAlert size={20} class="text-red-500" />{/if}
        {statusFilter === 'pending' ? 'Wachtende verzoeken' : statusFilter === 'approved' ? 'Goedgekeurde verzoeken' : 'Afgewezen verzoeken'}
      </h3>
      <button 
        onclick={fetchRequests} 
        disabled={loading}
        class="text-spotify-lightgray hover:text-white transition-colors disabled:opacity-50"
      >
        <RefreshCw size={18} class={loading ? 'animate-spin' : ''} />
      </button>
    </div>

    <div class="min-h-[200px]">
      {#if loading && requests.length === 0}
        <div class="flex items-center justify-center p-20">
          <RefreshCw class="animate-spin text-spotify-green" size={32} />
        </div>
      {:else if requests.length === 0}
        <div class="flex flex-col items-center justify-center p-20 text-spotify-lightgray">
          <UserPlus size={48} class="mb-4 opacity-20" />
          <p>Geen verzoeken gevonden met status '{statusFilter}'.</p>
        </div>
      {:else}
        <div class="overflow-x-auto">
          <table class="w-full text-left text-sm">
            <thead>
              <tr class="bg-white/5 text-spotify-lightgray text-[10px] uppercase tracking-wider">
                <th class="p-4">Gebruiker</th>
                <th class="p-4">Datum aangevraagd</th>
                {#if statusFilter !== 'pending'}
                  <th class="p-4">Beoordeeld door</th>
                  <th class="p-4">Datum beoordeeld</th>
                {/if}
                {#if statusFilter === 'pending'}
                  <th class="p-4 text-right">Acties</th>
                {/if}
              </tr>
            </thead>
            <tbody class="divide-y divide-spotify-gray divide-opacity-30">
              {#each requests as request (request.id)}
                <tr class="hover:bg-white/5 transition-colors">
                  <td class="p-4">
                    <div class="flex items-center gap-3">
                      {#if request.avatar_url}
                        <img src={request.avatar_url} alt="" class="w-10 h-10 rounded-full" />
                      {:else}
                        <div class="w-10 h-10 bg-white/10 rounded-full flex items-center justify-center">
                          <User size={20} class="text-spotify-lightgray" />
                        </div>
                      {/if}
                      <div>
                        <div class="font-bold">{request.display_name}</div>
                        <div class="text-xs text-spotify-lightgray">{request.email}</div>
                      </div>
                    </div>
                  </td>
                  <td class="p-4 text-spotify-lightgray">
                    {new Date(request.requested_at).toLocaleString('nl-NL')}
                  </td>
                  {#if statusFilter !== 'pending'}
                    <td class="p-4">
                      <span class="text-xs bg-white/5 px-2 py-1 rounded">
                        {request.reviewed_by_user_id || 'Systeem'}
                      </span>
                    </td>
                    <td class="p-4 text-spotify-lightgray">
                      {request.reviewed_at ? new Date(request.reviewed_at).toLocaleString('nl-NL') : '—'}
                    </td>
                  {/if}
                  {#if statusFilter === 'pending'}
                    <td class="p-4 text-right">
                      <div class="flex justify-end gap-2">
                        {#if hasPermission('user-requests.approve')}
                          <button 
                            onclick={() => confirmingAction = { type: 'approve', request }}
                            class="bg-spotify-green text-black px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                          >
                            <CheckCircle size={14} /> Goedkeuren
                          </button>
                        {/if}
                        {#if hasPermission('user-requests.reject')}
                          <button 
                            onclick={() => confirmingAction = { type: 'reject', request }}
                            class="bg-red-500/10 text-red-500 border border-red-500/20 px-3 py-1.5 rounded-full font-bold text-xs transition-transform hover:scale-105 flex items-center gap-1"
                          >
                            <XCircle size={14} /> Afwijzen
                          </button>
                        {/if}
                      </div>
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
  <div class="bg-[#282828] p-8 rounded-xl border border-white border-opacity-10 max-w-md w-full shadow-2xl">
    <h3 class="text-2xl font-bold mb-4 flex items-center gap-2">
      {#if confirmingAction.type === 'approve'}
        <CheckCircle class="text-spotify-green" /> Verzoek goedkeuren?
      {:else}
        <ShieldAlert class="text-red-500" /> Verzoek afwijzen?
      {/if}
    </h3>
    <p class="text-spotify-lightgray mb-6">
      {#if confirmingAction.type === 'approve'}
        Weet je zeker dat je de toegangsaanvraag van <b>{confirmingAction.request.display_name}</b> wilt goedkeuren? Er wordt direct een nieuw gebruikersaccount aangemaakt.
      {:else}
        Weet je zeker dat je de toegangsaanvraag van <b>{confirmingAction.request.display_name}</b> wilt afwijzen?
      {/if}
    </p>
    <div class="flex gap-4">
      <button 
        class="flex-1 py-3 rounded-full font-bold transition-all {confirmingAction.type === 'approve' ? 'bg-spotify-green text-black hover:scale-105' : 'bg-red-600 text-white hover:bg-red-700'}"
        onclick={() => confirmingAction.type === 'approve' ? approveRequest(confirmingAction.request) : rejectRequest(confirmingAction.request)}
      >
        {confirmingAction.type === 'approve' ? 'Bevestig goedkeuring' : 'Bevestig afwijzing'}
      </button>
      <button 
        class="flex-1 py-3 rounded-full font-bold bg-white/10 text-white hover:bg-white/20 transition-all"
        onclick={() => confirmingAction = null}
      >
        Annuleren
      </button>
    </div>
  </div>
</div>
{/if}
