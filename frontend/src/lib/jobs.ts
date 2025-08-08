import { writable } from 'svelte/store';

export interface Job {
  id: string;
  step: string;
  status: string;
}

export const jobs = writable<Job[]>([]);

export function upsert(job: Job) {
  jobs.update((current) => {
    const idx = current.findIndex((j) => j.id === job.id);
    if (["done", "error"].includes(job.status)) {
      if (idx >= 0) {
        return [...current.slice(0, idx), ...current.slice(idx + 1)];
      }
      return current;
    }
    if (idx >= 0) {
      const updated = [...current];
      updated[idx] = job;
      return updated;
    }
    return [job, ...current];
  });
}
