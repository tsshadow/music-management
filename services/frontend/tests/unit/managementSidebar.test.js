import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/svelte';
import { get } from 'svelte/store';
import ManagementSidebar from '../../src/lib/management/ManagementSidebar.svelte';
import { activeManagementTab, mumaUser, userPermissions } from '../../src/lib/store.js';
import { MANAGEMENT_TABS } from '../../src/lib/router.js';

describe('ManagementSidebar', () => {
  beforeEach(() => {
    activeManagementTab.set('overview');
    mumaUser.set({ id: 1, username: 'user', is_admin: false });
    userPermissions.set([]);
    globalThis.fetch = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('lists the tabs everyone may see', () => {
    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.getByText('Bibliotheek')).toBeTruthy();
    expect(screen.getByText('Downloaders')).toBeTruthy();
    expect(screen.getByText('Genre Curatie')).toBeTruthy();
    expect(screen.getByText('Over')).toBeTruthy();
  });

  it('the user tabs stay hidden without the permission', () => {
    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.queryByText('Gebruikers')).toBeNull();
    expect(screen.queryByText('Toegangsverzoeken')).toBeNull();
  });

  it('the user tab appears with the permission to read users', () => {
    userPermissions.set(['users.read']);

    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.getByText('Gebruikers')).toBeTruthy();
  });

  it('the access-request tab appears with its own permission', () => {
    userPermissions.set(['user-requests.read']);

    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.getByText('Toegangsverzoeken')).toBeTruthy();
  });

  it('an administrator sees every tab', () => {
    mumaUser.set({ id: 1, username: 'user', is_admin: true });

    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.getByText('Gebruikers')).toBeTruthy();
    expect(screen.getByText('Toegangsverzoeken')).toBeTruthy();
  });

  it('picking a tab switches to it', async () => {
    render(ManagementSidebar, { onnavigate: vi.fn() });

    await fireEvent.click(screen.getByText('Downloaders'));

    expect(get(activeManagementTab)).toBe('downloaders');
  });

  it('every tab an administrator can open has a route', async () => {
    mumaUser.set({ id: 1, username: 'user', is_admin: true });
    userPermissions.set(['users.read', 'user-requests.read', 'radio.manage']);
    const { container } = render(ManagementSidebar, { onnavigate: vi.fn() });

    // Clicking is the only way to learn a tab's id from the outside; the
    // sidebar keeps its own list, and a tab added there but not to the routing
    // table would silently lose its URL.
    const reached = [];
    for (const button of container.querySelectorAll('nav button')) {
      await fireEvent.click(button);
      reached.push(get(activeManagementTab));
    }

    expect(reached.length).toBeGreaterThan(0);
    expect(reached.filter((tab) => !MANAGEMENT_TABS.includes(tab))).toEqual([]);
  });

  it('the tab that is open is marked as such', async () => {
    activeManagementTab.set('health');

    render(ManagementSidebar, { onnavigate: vi.fn() });

    expect(screen.getByText('Gezondheid').className).toContain('text-white');
  });
});
