<script>
  import { t, locale } from './i18n/index.js';
  import MumaMark from './MumaMark.svelte';
  import { credentials, mumaApiUrl, mumaApiKey, mumaRefreshToken, mumaSessionActive, userPermissions, mumaUser, signedOut, ensureSubsonicToken, withoutPassword } from './store.js';
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
  // Inside the Android shell Google's web sign-in cannot run (Google refuses OAuth in a WebView),
  // so the shell does it natively and this page only shows a button for it -- when the APK was
  // built with a client ID. A browser tab keeps the Google Identity Services button.
  let nativeGoogle = $state(false);
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
    } else {
      // The password has done its job; not even this screen keeps it (issue #101).
      password = '';
      if (isNative) {
        // Hands the session to Kotlin, so downloads and Android Auto see it too -- without this a
        // sign-in typed here only ever lived in the WebView, and a download right after would
        // still look logged out. The account's own spelling of the name, not the typed one: the
        // phone signs every Subsonic call with it
        // (docs/bug-reports/074-login-case-forks-user-identity.md).
        await saveNativeSession(result.username || username);
      }
    }
    isLoading = false;
  }

  /**
   * Hands the session just started to the phone: the name, the MuMa API key and the account id --
   * never the password, which neither side keeps (issue #101). Never lets a bridge failure surface
   * as a login error: the web session is already live at this point, and losing the native copy
   * only degrades the native-only features, it does not undo the sign-in.
   *
   * @param {string} verifiedUsername
   */
  async function saveNativeSession(verifiedUsername) {
    try {
      await platform.system.saveCredentials({
        url: server,
        username: verifiedUsername,
        mumaApiKey: $mumaApiKey,
        mumaUserId: $mumaUser?.id ?? 0,
      });
    } catch (e) {
      console.warn('Could not hand the session to the phone', e);
    }
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
        error = data.detail || $t('login.setupFailed');
      }
    } catch (e) {
      error = $t('login.noManagementConnection');
    } finally {
      isLoading = false;
    }
  }

  /**
   * Handles a Google ID token -- from Google Identity Services in a browser, or from the Android
   * shell's native sign-in ({@link nativeGoogleSignIn}).
   *
   * Inside the shell the session goes to Kotlin as well, exactly as a password sign-in's does, so
   * downloads and Android Auto see the same session.
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
        // The name drives every Subsonic call (they are signed with the account's token, fetched
        // with the key just received) and the profile display name -- without it the user would
        // appear logged in but see no music and "Gebruiker" instead of their name. No password
        // is stored: the key used to be kept as one here, and neither side needs it (issue #101).
        username = data.user.username;
        save();
        signedOut.set(false);
        ensureSubsonicToken();
        if (isNative) await saveNativeSession(data.user.username);
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
        error = data.detail || $t('login.accessRequestFailed');
      }
    } catch (e) {
      error = $t('login.accessRequestError');
    } finally {
      isLoading = false;
    }
  }

  /**
   * "Sign in with Google" inside the Android shell: the shell shows Google's account chooser and
   * returns an ID token, which goes through {@link handleGoogleResponse} like the browser's does.
   * A closed chooser is no error; anything else is shown with the reason the shell gave.
   */
  async function nativeGoogleSignIn() {
    error = '';
    applyServer();
    let token;
    try {
      token = await platform.system.googleSignIn();
    } catch (e) {
      error = e?.code === 'no-credential'
        ? $t('login.googleNoCredential')
        : $t('login.googleFailed', { reason: e?.message || e?.code || '?' });
      return;
    }
    if (token) await handleGoogleResponse({ credential: token });
  }

  /** Leaves the access-request screens and shows the login form again. */
  function retryGoogleLogin() {
    requestStatus = null;
    googleUser = null;
    googleRequest = null;
  }

  /**
   * Saves the verified name to the global store -- the name only, never the password (issue #101).
   */
  function save() {
    credentials.update(c => ({ ...withoutPassword(c), username }));
  }

  import { onMount } from 'svelte';
  onMount(async () => {
    if ($credentials.username) {
        username = $credentials.username;
    }
    if (isNative) {
        server = platform.system.serverUrl().subsonic || $credentials.url;
    }

    if (isNative) {
      nativeGoogle = await platform.system.googleSignInAvailable();
    } else if (GOOGLE_CLIENT_ID) {
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
  <div class="bg-muma-spotify-panel border border-muma-spotify-light p-10 rounded-2xl w-full max-w-md flex flex-col gap-6 shadow-2xl">
    <div class="flex flex-col items-center gap-2 mb-2">
      <div class="w-14 h-14 bg-brand rounded-full flex items-center justify-center text-black mb-1">
        <MumaMark size={32} />
      </div>
      <h1 class="text-3xl font-extrabold tracking-tight m-0">MuMa</h1>
      <h2 class="text-sm font-medium text-muma-spotify-text m-0">{setupRequired ? $t('login.setupTitle') : $t('login.title')}</h2>
    </div>
    
    {#if requestStatus === 'unknown'}
      <div class="flex flex-col gap-4 text-center">
        {#if googleUser.avatar_url}
          <img src={googleUser.avatar_url} alt={$t('login.avatar')} class="w-20 h-20 rounded-full mx-auto" />
        {/if}
        <p class="text-sm">{$t('login.noAccessYet', { name: googleUser.display_name, email: googleUser.email })}</p>
        <button class="bg-brand-green hover:bg-[#1ed760] text-black border-none rounded-full p-3.5 text-base font-bold cursor-pointer transition-transform hover:scale-[1.02] disabled:opacity-50" onclick={requestAccess} disabled={isLoading}>
          {isLoading ? $t('common.busy') : $t('login.requestAccess')}
        </button>
        <button class="text-muma-spotify-text text-sm hover:underline bg-transparent border-none cursor-pointer" onclick={retryGoogleLogin}>{$t('login.backToLogin')}</button>
      </div>
    {:else if requestStatus === 'pending'}
      <div class="flex flex-col gap-4 text-center">
        <div class="bg-blue-500/20 text-blue-400 p-4 rounded-lg text-sm">
          {$t('login.requestPending')}
        </div>
        <p class="text-xs text-muma-spotify-text">{$t('login.requestedOn', { date: new Date(googleRequest.requested_at).toLocaleString($locale) })}</p>
        <button class="text-muma-spotify-text text-sm hover:underline bg-transparent border-none cursor-pointer" onclick={retryGoogleLogin}>{$t('login.backToLogin')}</button>
      </div>
    {:else if requestStatus === 'rejected'}
      <div class="flex flex-col gap-4 text-center">
        <div class="bg-red-500/20 text-red-400 p-4 rounded-lg text-sm">
          {$t('login.requestRejected')}
        </div>
        <button class="text-muma-spotify-text text-sm hover:underline bg-transparent border-none cursor-pointer" onclick={retryGoogleLogin}>{$t('login.backToLogin')}</button>
      </div>
    {:else if requestStatus === 'approved'}
      <div class="flex flex-col gap-4 text-center">
        <div class="bg-green-500/20 text-green-400 p-4 rounded-lg text-sm">
          {$t('login.requestApproved')}
        </div>
        <button class="bg-brand-green hover:bg-[#1ed760] text-black border-none rounded-full p-3.5 text-base font-bold cursor-pointer transition-transform hover:scale-[1.02]" onclick={retryGoogleLogin}>
          {$t('login.loginNow')}
        </button>
      </div>
    {:else}
      <p class="text-sm text-muma-spotify-text text-center m-0">
        {setupRequired 
          ? $t('login.setupIntro')
          : $t('login.intro')}
      </p>

      {#if error}
        <div class="bg-[#e91429] text-white p-3 rounded-lg text-sm font-medium">{error}</div>
      {/if}

      {#if isNative}
        <div class="flex flex-col gap-2">
          <label for="server" class="text-xs font-bold text-muma-spotify-text uppercase tracking-wider">{$t('login.server')}</label>
          <input id="server" type="url" inputmode="url" autocomplete="url" value={server} oninput={(e) => server = e.target.value} placeholder="https://muma.example" class="bg-[#2a2a2a] border border-transparent rounded-lg p-3 text-white text-sm focus:outline-none focus:border-brand-green disabled:opacity-50" disabled={isLoading} />
          <p class="text-[11px] text-muma-spotify-text m-0">{$t('login.serverHint')}</p>
        </div>
      {/if}
      <div class="flex flex-col gap-2">
        <label for="username" class="text-xs font-bold text-muma-spotify-text uppercase tracking-wider">{$t('login.username')}</label>
        <input id="username" type="text" value={username} oninput={(e) => username = e.target.value} placeholder={$t('login.username')} class="bg-[#2a2a2a] border border-transparent rounded-lg p-3 text-white text-sm focus:outline-none focus:border-brand-green disabled:opacity-50" disabled={isLoading} />
      </div>
      <div class="flex flex-col gap-2">
        <label for="password" class="text-xs font-bold text-muma-spotify-text uppercase tracking-wider">{$t('login.password')}</label>
        <input id="password" type="password" value={password} oninput={(e) => password = e.target.value} placeholder={$t('login.password')} class="bg-[#2a2a2a] border border-transparent rounded-lg p-3 text-white text-sm focus:outline-none focus:border-brand-green disabled:opacity-50" disabled={isLoading} onkeydown={(e) => e.key === 'Enter' && (setupRequired ? performSetup() : verifyLogin())} />
      </div>
      <button class="bg-brand-green hover:bg-[#1ed760] text-black border-none rounded-full p-3.5 text-base font-extrabold cursor-pointer transition-transform hover:scale-[1.02] disabled:opacity-50 mt-2" onclick={setupRequired ? performSetup : verifyLogin} disabled={isLoading}>
        {isLoading ? (setupRequired ? $t('login.settingUp') : $t('login.verifying')) : (setupRequired ? $t('login.createAccount') : $t('login.connect'))}
      </button>

      {#if !setupRequired && (nativeGoogle || (!isNative && GOOGLE_CLIENT_ID))}
        <div class="flex items-center gap-4 my-2">
          <div class="h-[1px] bg-[#2a2a2a] flex-1"></div>
          <span class="text-xs text-muma-spotify-text font-bold uppercase">{$t('login.or')}</span>
          <div class="h-[1px] bg-[#2a2a2a] flex-1"></div>
        </div>

        {#if nativeGoogle}
          <!-- Native Google sign-in (styleguide: "Sign in with Google" button) -->
          <button type="button" class="flex items-center justify-center gap-3 w-full bg-white text-[#1f1f1f] border border-[#747775] rounded-full p-3 text-sm font-medium cursor-pointer disabled:opacity-50" onclick={nativeGoogleSignIn} disabled={isLoading}>
            <svg aria-hidden="true" width="18" height="18" viewBox="0 0 48 48"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>
            {$t('login.googleSignIn')}
          </button>
        {:else}
          <div id="googleBtn" class="flex justify-center w-full"></div>
        {/if}
      {/if}
    {/if}
  </div>
</div>

<style>
</style>
