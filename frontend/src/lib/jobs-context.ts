import { writable, type Writable } from 'svelte/store';
import { getContext, setContext } from 'svelte';
import { jobs as jobsStore, upsert, type Job } from './jobs';

const API_BASE = import.meta.env.VITE_API_BASE || '/api';
const WS_URL = API_BASE
  ? API_BASE.replace(/^http/, 'ws').replace(/\/?api$/, '') + '/ws/jobs'
  : typeof window !== 'undefined'
    ? window.location.origin.replace(/^http/, 'ws') + '/ws/jobs'
    : '';

class JobsContext {
  steps: Writable<string[]> = writable([]);
  jobs = jobsStore;

  constructor() {
    if (typeof window !== 'undefined') {
      this.loadSteps();
      this.loadJobs();
      this.setupWebSocket();
    }
  }

  async loadSteps() {
    try {
      const res = await fetch(`${API_BASE}/steps`);
      const data = await res.json();
      this.steps.set(data.steps ?? []);
    } catch {
      this.steps.set([]);
    }
  }

  async loadJobs() {
    try {
      const res = await fetch(`${API_BASE}/jobs`);
      const data = await res.json();
      (data.jobs ?? [])
        .filter((j: Job) => ['queued', 'running'].includes(j.status))
        .forEach(upsert);
    } catch {
      // ignore errors
    }
  }

  setupWebSocket() {
    if (typeof WebSocket === 'undefined') return;
    try {
      const ws = new WebSocket(WS_URL);
      ws.onmessage = ev => {
        const update = JSON.parse(ev.data);
        upsert(update);
      };
    } catch {
      // ignore errors
    }
  }

  async start(step: string, options: Record<string, unknown> = {}) {
    try {
      const res = await fetch(`${API_BASE}/run/${step}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(options),
      });
      const job = await res.json();
      upsert(job);
      return job as Job;
    } catch {
      return null;
    }
  }

  async stop(jobId: string) {
    try {
      await fetch(`${API_BASE}/job/${jobId}/stop`, { method: 'POST' });
    } catch {
      // ignore
    }
  }

  async get(jobId: string) {
    try {
      const res = await fetch(`${API_BASE}/job/${jobId}`);
      return (await res.json()) as Job;
    } catch {
      return null;
    }
  }
}

const key = Symbol('JobsContext');

export function initializeJobsContext() {
  setContext(key, new JobsContext());
}

export function getJobsContext(): JobsContext {
  return getContext<JobsContext>(key);
}
