<script>
  import { t, locale } from './i18n/index.js';
  import MumaMark from './MumaMark.svelte';
  import { credentials, mumaApiUrl, mumaApiKey, mumaRefreshToken, mumaSessionActive, userPermissions, mumaUser } from './store.js';
  import { signIn } from './login.js';
  import { platform } from './platform/index.js';

  let username = $state('');
  let password = $state('');
  let error = $state('');
  let isLoading = $state(false);
  let setupRequired = $state(false);

  // The browser knows its server: the page came from it. Inside the Android
  // shell the page came from `https://localhost`, so the server is a field --
  // prefilled from what the phone is signed in to, and editable, because a
  // first run against a new server is exactly when it is wrong.
  const isNative = platform.system.isNative;
  let server = $state('');

  /**
   * Points the app at the typed server before anything is verified against it.
   * Native only; on the web `credentials.url` is derived from the location and
   * must stay that way.
   */
  function applyServer() {
    if (!isNative) return;
    credentials.update(c => ({ ...c, url: server.trim().replace(/\/+$/, '') }));
  }

  const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID;
  let requestStatus = $state(null); // 'unknown', 'pending', 'approved', 'rejected'
  let googleUser = $state(null);
  let googleRequest = $state(null);
  let idToken = '';

  /**
   * Verifies the provided credentials by pinging the Subsonic API.
   */
  async function verifyLogin() {
    error = '';
    isLoading = true;
    applyServer();

    // `signIn` is the one sign-in path in the app: this screen and the Android
    // shell's silent boot login both go through it, so "signed in" has one
    // definition. It never throws; a failure comes back as a reason and this
    // screen turns it into a sentence.
    const result = await signIn(username, password);
    if (!result.ok) {
      error = result.reason === 'offline'
        ? $t('login.noServerConnection')
        : `Fout: ${result.message || $t('login.invalidCredentials')}`;
    }
    isLoading = false;
  }

  /** Gives the phone back to the Kotlin interface. Native only. */
  function backToLegacyUi() {
    platform.system.switchToLegacyUi();
  }

  /**
   * Performs the initial administrative setup.
   */
  async function performSetup() {
    error = '';
    isLoading = true;

    try {
      const response = await fetch(`${$mumaApiUrl}/api/auth/setup`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          username,
          password,
          display_name: username,
          role_name: 'admin'
        })
      });

      if (response.ok) {
        setupRequired = false;
        // Give the server a moment to sync the new user
        error = '';
        setTimeout(verifyLogin, 1000);
      } else {
        const data = await response.json();
        error = data.detail || 'Setup mislukt';
      }
    } catch (e) {
      error = 'Kon geen verbinding maken met de management API';
    } finally {
      isLoading = false;
    }
  }

  /**
   * Handles the response from Google Identity Services.
   */
  async function handleGoogleResponse(response) {
    idToken = response.credential;
    isLoading = true;
    error = '';
    
    try {
      const res = await fetch(`${$mumaApiUrl}/api/auth/google`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id_token: idToken })
      });
      
      const data = await res.json();
      
      if (data.status === 'ok') {
        mumaApiKey.set(data.api_key);
        mumaRefreshToken.set(data.refresh_token);
        userPermissions.set(data.user.permissions);
        mumaUser.set(data.user);
        mumaSessionActive.set(true);
        // A Google sign-in never learns the account's real Subsonic password, but the
        // `credentials` store (username/password) drives every Subsonic/LMS call (genres,
        // albums, streaming, ...) and the profile display name -- without this, the user
        // would appear logged in but see no music and "Gebruiker" instead of their name.
        // The backend accepts the api_key itself as a valid password for this account (see
        // `login()` in users.py), so use that as the Subsonic credential.
        username = data.user.username;
        password = data.api_key;
        save();
      } else if (data.status === 'unknown') {
        requestStatus = 'unknown';
        googleUser = data.google;
      } else if (['request_pending', 'request_approved', 'request_rejected'].includes(data.status)) {
        requestStatus = data.status.replace('request_', '');
        googleRequest = data.request;
      }
    } catch (e) {
      error = $t('login.noGoogleConnection');
    } finally {
      isLoading = false;
    }
  }

  /**
   * Submits an access request using the Google ID token.
   */
  async function requestAccess() {
    isLoading = true;
    error = '';
    try {
      const res = await fetch(`${$mumaApiUrl}/api/auth/access-request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id_token: idToken })
      });
      const data = await res.json();
      if (data.status === 'ok') {
        requestStatus = 'pending';
        googleRequest = data.request;
      } else {
        error = data.detail || 'Toegangsaanvraag mislukt';
      }
    } catch (e) {
      error = 'Fout bij indienen toegangsaanvraag';
    } finally {
      isLoading = false;
    }
  }

  function retryGoogleLogin() {
    requestStatus = null;
    googleUser = null;
    googleRequest = null;
  }

  /**
   * Saves the verified credentials to the global store.
   */
  function save() {
    credentials.update(c => ({ ...c, username, password }));
  }

  import { onMount } from 'svelte';
  onMount(async () => {
    if ($credentials.username) {
        username = $credentials.username;
        password = $credentials.password;
    }
    if (isNative) {
        server = platform.system.serverUrl().subsonic || $credentials.url;
    }

    if (GOOGLE_CLIENT_ID) {
      const script = document.createElement('script');
      script.src = 'https://accounts.google.com/gsi/client';
      script.async = true;
      script.defer = true;
      script.onload = () => {
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: handleGoogleResponse
        });
        window.google.accounts.id.renderButton(
          document.getElementById("googleBtn"),
          { theme: "outline", size: "large", width: 336, text: "signin_with", locale: "nl" }
        );
      };
      document.head.appendChild(script);
    }

    try {
      const res = await fetch(`${$mumaApiUrl}/api/auth/setup-status`);
      if (res.ok) {
        const data = await res.json();
        setupRequired = data.setup_required;
      }
    } catch (e) {
      console.warn('Could not check setup status', e);
    }
  });
</script>

<div class="min-h-screen w-screen bg-black flex flex-col justify-center items-center p-4 text-white">
  <div class="bg-[#181818] border border-[#282828] p-10 rounded-2xl w-full max-w-md flex flex-col gap-6 shadow-2xl">
    <div class="flex flex-col items-center gap-2 mb-2">
      <div class="w-14 h-14 bg-brand rounded-full flex items-center justify-center text-black mb-1">
        <MumaMark size={32} />
      </div>
      <h1 class="text-3xl font-extrabold tracking-tight m-0">MuMa</h1>
      <h2 class="text-sm font-medium text-[#b3b3b3] m-0">{setupRequired ? $t('login.setupTitle') : $t('login.title')}</h2>
    </div>
    
    {#if requestStatus === 'unknown'}
      <div class="flex flex-col gap-4 text-center">
        {#if googleUser.avatar_url}
          <img src={googleUser.avatar_url} alt={$t('login.avatar')} class="w-20 h-20 rounded-full mx-auto" />
        {/if}
        <p class="text-sm">{$t('login.noAccessYet', { name: googleUser.display_name, email: googleUser.email })}</p>
        <button class="bg-[#1db954] hover:bg-[#1ed760] text-black border-none rounded-full p-3.5 text-base font-bold cursor-pointer transition-transform hover:scale-[1.02] disabled:opacity-50" onclick={requestAccess} disabled={isLoading}>
          {isLoading ? $t('common.busy') : $t('login.requestAccess')}
        </button>
        <button class="text-[#b3b3b3] text-sm hover:underline bg-transparent border-none cursor-pointer" onclick={retryGoogleLogin}>{$t('login.backToLogin')}</button>
      </div>
    {:else if requestStatus === 'pending'}
      <div class="flex flex-col gap-4 text-center">
        <div class="bg-blue-500/20 text-blue-400 p-4 rounded-lg text-sm">
          {$t('login.requestPending')}
        </div>
        <p class="text-xs text-[#b3b3b3]">{$t('login.requestedOn', { date: new Date(googleRequest.requested_at).toLocaleString($locale) })}</p>
        <button class="text-[#b3b3b3] text-sm hover:underline bg-transparent border-none cursor-pointer" onclick={retryGoogleLogin}>{$t('login.backToLogin')}</button>
      </div>
    {:else if requestStatus === 'rejected'}
      <div class="flex flex-col gap-4 text-center">
        <div class="bg-red-500/20 text-red-400 p-4 rounded-lg text-sm">
          {$t('login.requestRejected')}
        </div>
        <button class="text-[#b3b3b3] text-sm hover:underline bg-transparent border-none cursor-pointer" onclick={retryGoogleLogin}>{$t('login.backToLogin')}</button>
      </div>
    {:else if requestStatus === 'approved'}
      <div class="flex flex-col gap-4 text-center">
        <div class="bg-green-500/20 text-green-400 p-4 rounded-lg text-sm">
          {$t('login.requestApproved')}
        </div>
        <button class="bg-[#1db954] hover:bg-[#1ed760] text-black border-none rounded-full p-3.5 text-base font-bold cursor-pointer transition-transform hover:scale-[1.02]" onclick={retryGoogleLogin}>
          {$t('login.loginNow')}
        </button>
      </div>
    {:else}
      <p class="text-sm text-[#b3b3b3] text-center m-0">
        {setupRequired 
          ? $t('login.setupIntro')
          : $t('login.intro')}
      </p>

      {#if error}
        <div class="bg-[#e91429] text-white p-3 rounded-lg text-sm font-medium">{error}</div>
      {/if}

      {#if isNative}
        <div class="flex flex-col gap-2">
          <label for="server" class="text-xs font-bold text-[#b3b3b3] uppercase tracking-wider">{$t('login.server')}</label>
          <input id="server" type="url" inputmode="url" autocomplete="url" value={server} oninput={(e) => server = e.target.value} placeholder="https://muma.example" class="bg-[#2a2a2a] border border-transparent rounded-lg p-3 text-white text-sm focus:outline-none focus:border-[#1db954] disabled:opacity-50" disabled={isLoading} />
          <p class="text-[11px] text-[#b3b3b3] m-0">{$t('login.serverHint')}</p>
        </div>
      {/if}
      <div class="flex flex-col gap-2">
        <label for="username" class="text-xs font-bold text-[#b3b3b3] uppercase tracking-wider">{$t('login.username')}</label>
        <input id="username" type="text" value={username} oninput={(e) => username = e.target.value} placeholder={$t('login.username')} class="bg-[#2a2a2a] border border-transparent rounded-lg p-3 text-white text-sm focus:outline-none focus:border-[#1db954] disabled:opacity-50" disabled={isLoading} />
      </div>
      <div class="flex flex-col gap-2">
        <label for="password" class="text-xs font-bold text-[#b3b3b3] uppercase tracking-wider">{$t('login.password')}</label>
        <input id="password" type="password" value={password} oninput={(e) => password = e.target.value} placeholder={$t('login.password')} class="bg-[#2a2a2a] border border-transparent rounded-lg p-3 text-white text-sm focus:outline-none focus:border-[#1db954] disabled:opacity-50" disabled={isLoading} onkeydown={(e) => e.key === 'Enter' && (setupRequired ? performSetup() : verifyLogin())} />
      </div>
      <button class="bg-[#1db954] hover:bg-[#1ed760] text-black border-none rounded-full p-3.5 text-base font-extrabold cursor-pointer transition-transform hover:scale-[1.02] disabled:opacity-50 mt-2" onclick={setupRequired ? performSetup : verifyLogin} disabled={isLoading}>
        {isLoading ? (setupRequired ? $t('login.settingUp') : $t('login.verifying')) : (setupRequired ? $t('login.createAccount') : $t('login.connect'))}
      </button>

      {#if !setupRequired && GOOGLE_CLIENT_ID}
        <div class="flex items-center gap-4 my-2">
          <div class="h-[1px] bg-[#2a2a2a] flex-1"></div>
          <span class="text-xs text-[#b3b3b3] font-bold uppercase">{$t('login.or')}</span>
          <div class="h-[1px] bg-[#2a2a2a] flex-1"></div>
        </div>

        <div id="googleBtn" class="flex justify-center w-full"></div>
      {/if}
    {/if}

    {#if isNative}
      <!-- The Kotlin interface is still in the APK and still the default; this
           is the way back out of the beta without reinstalling anything. -->
      <button class="text-[#b3b3b3] text-sm hover:underline bg-transparent border-none cursor-pointer mt-2" onclick={backToLegacyUi}>
        {$t('login.backToLegacyUi')}
      </button>
    {/if}
  </div>
</div>

<style>
</style>
