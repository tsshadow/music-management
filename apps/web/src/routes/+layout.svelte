<script lang="ts">
  import '$lib/theme.css';
  import '@fontsource/inter/variable.css';
  import { page } from '$app/stores';

  const links = [
    { href: '/', label: 'Overview' },
    { href: '/importer', label: 'Importer' },
    { href: '/scrobbler', label: 'Scrobbler & Analyzer' }
  ];
</script>

<main>
  <div class="shell">
    <nav>
      <div class="brand">MuMa Control Center</div>
      <ul>
        {#each links as link}
          <li>
            <a href={link.href} class:active={$page.url.pathname === link.href}>
              {link.label}
            </a>
          </li>
        {/each}
      </ul>
    </nav>
    <slot />
  </div>
</main>

<style>
  .shell {
    max-width: 1100px;
    margin: 0 auto;
    padding: 2.5rem 2rem 4rem;
  }

  nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 2.5rem;
  }

  .brand {
    font-size: 1.5rem;
    font-weight: 700;
  }

  ul {
    display: flex;
    gap: 1.5rem;
    list-style: none;
    margin: 0;
    padding: 0;
  }

  a {
    color: var(--color-muted);
    font-weight: 600;
    letter-spacing: 0.02em;
  }

  a.active {
    color: var(--color-primary);
  }
</style>
