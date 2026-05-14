import { describe, it, expect, beforeEach } from 'vitest';
import { jobs, upsert } from './jobs';
import { get } from 'svelte/store';

describe('jobs store', () => {
  beforeEach(() => {
    jobs.set([]);
  });

  it('upserts and removes jobs', () => {
    upsert({ id: '1', step: 'test', status: 'queued' });
    expect(get(jobs)).toHaveLength(1);
    upsert({ id: '1', step: 'test', status: 'running' });
    expect(get(jobs)[0].status).toBe('running');
    upsert({ id: '1', step: 'test', status: 'done' });
    expect(get(jobs)).toHaveLength(0);
  });
});
