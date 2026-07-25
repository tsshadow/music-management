import { describe, it, expect, beforeEach, vi } from 'vitest';
import { get, writable } from 'svelte/store';
import { hasPermission, userPermissions, mumaUser, authParams, credentials, mumaApiUrl } from '../../src/lib/store';

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

describe('store - authParams', () => {
  it('should return empty string when credentials are missing', () => {
    credentials.set({ username: '', password: '' });
    expect(get(authParams)).toBe('');
  });

  it('should return encoded query params when credentials are set', () => {
    credentials.set({ username: 'test_user', password: 'test_password' });
    const params = get(authParams);
    expect(params).toContain('u=test_user');
    expect(params).toContain('p=test_password');
    expect(params).toContain('v=1.12.0');
    expect(params).toContain('c=spotify');
  });

  it('should encode special characters in credentials', () => {
    credentials.set({ username: 'user@example.com', password: 'pass word' });
    const params = get(authParams);
    expect(params).toContain('u=user%40example.com');
    expect(params).toContain('p=pass%20word');
  });
});

describe('store - mumaApiUrl', () => {
  it('should have a default value', () => {
    const url = get(mumaApiUrl);
    expect(url).toBeDefined();
    expect(typeof url).toBe('string');
  });
});
