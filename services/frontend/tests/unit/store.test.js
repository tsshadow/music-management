import { describe, it, expect, beforeEach } from 'vitest';
import { get } from 'svelte/store';
import { hasPermission, userPermissions, mumaUser } from '../../src/lib/store';

describe('store - hasPermission', () => {
  beforeEach(() => {
    userPermissions.set([]);
    mumaUser.set(null);
  });

  it('should return false when user has no permissions and is not admin', () => {
    expect(hasPermission('music.read')).toBe(false);
  });

  it('should return true when user has the specific permission', () => {
    userPermissions.set(['music.read']);
    expect(hasPermission('music.read')).toBe(true);
  });

  it('should return true when user is admin via is_admin flag', () => {
    mumaUser.set({ is_admin: true });
    expect(hasPermission('any.permission')).toBe(true);
  });

  it('should return true when user has admin role name', () => {
    mumaUser.set({ role_name: 'admin' });
    expect(hasPermission('any.permission')).toBe(true);
  });

  it('should return false for other permissions if only one is granted', () => {
    userPermissions.set(['music.read']);
    expect(hasPermission('users.read')).toBe(false);
  });
});
