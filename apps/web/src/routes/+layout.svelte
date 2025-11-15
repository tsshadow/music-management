<script lang="ts">
  /** Application shell with persistent navigation across importer and scrobbler sections. */
  import '../app.css';
  import { page } from '$app/stores';

  let { children } = $props();

  type NavLink = { href: string; label: string };

  const links: NavLink[] = [
    { href: '/importer', label: 'Importer' },
    { href: '/library', label: 'Library' },
    { href: '/scrobbles', label: 'Scrobbles' },
    { href: '/config', label: 'Config' },
  ];

  function isActive(pathname: string, href: string): boolean {
    if (href === '/') {
      return pathname === '/';
    }
    return pathname === href || pathname.startsWith(`${href}/`);
  }
</script>

<svelte:head>
  <title>MuMa Music Management</title>
</svelte:head>

<div class="app-shell">
  <header class="app-header">
    <h1>MuMa</h1>
    <p>Unified control centre for importing, scrobbling, and tuning your library.</p>
    <nav aria-label="Primary navigation" class="primary-nav">
      {#each links as link}
        <a
          href={link.href}
          class:active={isActive($page.url.pathname, link.href)}
          aria-current={isActive($page.url.pathname, link.href) ? 'page' : undefined}
        >
          {link.label}
        </a>
      {/each}
    </nav>
  </header>

  <main class="app-content">
    {@render children()}
  </main>
</div>

<style>
  .app-shell {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    gap: 2rem;
  }

  .app-header {
    text-align: center;
    padding: 3rem 1rem 1rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    align-items: center;
  }

  .app-header h1 {
    margin: 0;
    font-size: clamp(2.5rem, 6vw, 3.5rem);
  }

  .app-header p {
    max-width: 48ch;
    margin: 0;
    color: rgba(255, 255, 255, 0.75);
  }

  .primary-nav {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
    justify-content: center;
    margin-top: 1rem;
  }

  .primary-nav a {
    text-decoration: none;
    padding: 0.6rem 1.5rem;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.08);
    color: inherit;
    transition: transform 0.2s ease, background 0.2s ease;
  }

  .primary-nav a:hover {
    transform: translateY(-2px);
    background: rgba(255, 255, 255, 0.16);
  }

  .primary-nav a.active {
    background: var(--accent-color);
    color: white;
  }

  .app-content {
    flex: 1;
    padding-bottom: 4rem;
  }
</style>
