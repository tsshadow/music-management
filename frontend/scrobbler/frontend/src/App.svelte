<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import Analyzer from './routes/Analyzer.svelte';
  import Dashboard from './routes/Dashboard.svelte';
  import Scrobbler from './routes/Scrobbler.svelte';
  import Settings from './routes/Settings.svelte';

  /** Root application shell providing lightweight client-side routing. */
  type Route = '/' | '/scrobbler' | '/analyzer' | '/settings';

  const routes: Record<Route, typeof Dashboard> = {
    '/': Dashboard,
    '/scrobbler': Scrobbler,
    '/analyzer': Analyzer,
    '/settings': Settings,
  };

  const titles: Record<Route, string> = {
    '/': 'Overview',
    '/scrobbler': 'Scrobbler',
    '/analyzer': 'Analyzer',
    '/settings': 'Settings',
  };

  function parseRoute(pathname: string): Route {
    if (pathname === '/scrobbler' || pathname === '/analyzer' || pathname === '/settings') {
      return pathname;
    }
    return '/';
  }

  let currentRoute: Route = typeof window !== 'undefined' ? parseRoute(window.location.pathname) : '/';

  function navigate(path: Route) {
    if (typeof window === 'undefined' || currentRoute === path) {
      return;
    }
    window.history.pushState({}, titles[path], path);
    currentRoute = path;
  }

  function onNavClick(event: MouseEvent, path: Route) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    navigate(path);
  }

  function handlePopState() {
    if (typeof window === 'undefined') {
      return;
    }
    currentRoute = parseRoute(window.location.pathname);
  }

  onMount(() => {
    window.addEventListener('popstate', handlePopState);
  });

  onDestroy(() => {
    window.removeEventListener('popstate', handlePopState);
  });
</script>

<main>
  <nav class="primary-nav">
    <a
      href="/"
      class:active={currentRoute === '/'}
      aria-current={currentRoute === '/' ? 'page' : undefined}
      on:click={(event) => onNavClick(event, '/')}
      >Overview</a
    >
    <a
      href="/scrobbler"
      class:active={currentRoute === '/scrobbler'}
      aria-current={currentRoute === '/scrobbler' ? 'page' : undefined}
      on:click={(event) => onNavClick(event, '/scrobbler')}
      >Scrobbler</a
    >
    <a
      href="/analyzer"
      class:active={currentRoute === '/analyzer'}
      aria-current={currentRoute === '/analyzer' ? 'page' : undefined}
      on:click={(event) => onNavClick(event, '/analyzer')}
      >Analyzer</a
    >
    <a
      href="/settings"
      class:active={currentRoute === '/settings'}
      aria-current={currentRoute === '/settings' ? 'page' : undefined}
      on:click={(event) => onNavClick(event, '/settings')}
      >Settings</a
    >
  </nav>

  {#if routes[currentRoute]}
    <svelte:component this={routes[currentRoute]} />
  {:else}
    <Dashboard />
  {/if}
</main>

<style>
  main {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .primary-nav {
    display: flex;
    justify-content: center;
    gap: 1rem;
    flex-wrap: wrap;
    margin-bottom: 1rem;
  }

  .primary-nav a {
    background: rgba(255, 255, 255, 0.05);
    border-radius: 999px;
    color: var(--text-color);
    padding: 0.75rem 1.5rem;
    text-decoration: none;
    transition: background 0.2s ease;
  }

  .primary-nav a.active {
    background: var(--accent-color);
    color: white;
  }
</style>
