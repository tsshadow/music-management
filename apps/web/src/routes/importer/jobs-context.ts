/** Manage importer jobs and websocket updates within the UI context. */
import { getContext, setContext } from 'svelte';
import { writable, type Writable } from 'svelte/store';
import { importerApi, websocketUrl } from '$lib/api';
import { jobs as jobsStore, upsert, type Job } from './jobs';

const STEPS_ENDPOINT = importerApi.url('/steps');
const JOBS_ENDPOINT = importerApi.url('/jobs');
const ACCOUNTS_ENDPOINT = importerApi.url('/accounts');
const RUN_ENDPOINT = importerApi.url('/run');
const JOB_ENDPOINT = importerApi.url('/job');
const JOB_SOCKET_URL = websocketUrl(importerApi.url('/ws/jobs'));

export class JobsContext {
  steps: Writable<string[]> = writable([]);
  jobs = jobsStore;
  accounts: Writable<{ soundcloud: string[]; youtube: string[] }> = writable({
    soundcloud: [],
    youtube: [],
  });

  constructor() {
    if (typeof window !== 'undefined') {
      this.loadSteps();
      this.loadJobs();
      this.loadAccounts();
      this.setupWebSocket();
    }
  }

  async loadSteps() {
    try {
      const res = await fetch(STEPS_ENDPOINT);
      const data = await res.json();
      this.steps.set(data.steps ?? []);
    } catch {
      this.steps.set([]);
    }
  }

  async loadJobs() {
    try {
      const res = await fetch(JOBS_ENDPOINT);
      const data = await res.json();
      (data.jobs ?? [])
        .filter((j: Job) => ['queued', 'running'].includes(j.status))
        .forEach(upsert);
    } catch {
      // ignore errors
    }
  }

  async loadAccounts() {
    try {
      const res = await fetch(ACCOUNTS_ENDPOINT);
      const data = await res.json();
      const soundcloud = Array.isArray(data.soundcloud) ? data.soundcloud : [];
      const youtube = Array.isArray(data.youtube) ? data.youtube : [];
      this.accounts.set({
        soundcloud: [...soundcloud].sort(),
        youtube: [...youtube].sort(),
      });
    } catch {
      this.accounts.set({ soundcloud: [], youtube: [] });
    }
  }

  setupWebSocket() {
    if (typeof WebSocket === 'undefined') return;
    const connect = () => {
      try {
        const ws = new WebSocket(JOB_SOCKET_URL);
        ws.onmessage = (event) => {
          const update = JSON.parse(event.data);
          upsert(update);
        };
        ws.onclose = () => {
          setTimeout(connect, 1000);
        };
        ws.onerror = () => {
          ws.close();
        };
      } catch {
        console.log('reconnecting...');
        setTimeout(connect, 1000);
      }
    };
    connect();
  }

  async start(step: string, options: Record<string, unknown> = {}) {
    try {
      const res = await fetch(`${RUN_ENDPOINT}/${step}`, {
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
      await fetch(`${JOB_ENDPOINT}/${jobId}/stop`, { method: 'POST' });
    } catch {
      // ignore
    }
  }

  async get(jobId: string) {
    try {
      const res = await fetch(`${JOB_ENDPOINT}/${jobId}`);
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
