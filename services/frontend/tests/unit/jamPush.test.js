import { describe, it, expect } from 'vitest';
import { shouldPushJamState } from '../../src/lib/radioSync';

describe('shouldPushJamState', () => {
  it('lets the host push', () => {
    expect(shouldPushJamState('host', false, true)).toBe(true);
  });

  it('blocks a radio follower from ever pushing', () => {
    expect(shouldPushJamState('follower-radio', false, true)).toBe(false);
  });

  it('blocks a jam follower from pushing unsolicited state', () => {
    expect(shouldPushJamState('follower-jam', false, true)).toBe(false);
  });

  it('blocks pushing when sync is off', () => {
    expect(shouldPushJamState('off', false, true)).toBe(false);
  });

  it('blocks pushing while a sync is in flight', () => {
    expect(shouldPushJamState('host', true, true)).toBe(false);
  });

  it('blocks pushing without credentials', () => {
    expect(shouldPushJamState('host', false, false)).toBe(false);
  });
});
