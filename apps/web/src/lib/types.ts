/** Shared importer data contracts used by the dashboard. */
export type DownloadTask = {
  source: 'youtube' | 'manual' | 'soundcloud' | 'telegram';
  target?: string | null;
  options: Record<string, unknown>;
};

export type DownloadedTrack = {
  source: string;
  location: string;
  metadata: Record<string, unknown>;
};

export type DownloadBatch = {
  job_id: string;
  created_at: string;
  tasks: DownloadTask[];
  tracks: DownloadedTrack[];
};

export type TaggingReport = {
  job_id: string;
  created_at: string;
  profile: string;
  mutations: { location: string }[];
};

export type ImporterJobStatus = {
  id: string;
  status: string;
  step?: string;
  started?: string;
  finished?: string;
  updated?: string;
  log: Record<string, unknown>[];
  error?: string;
  [key: string]: unknown;
};

export type JobRunSummary = {
  job_ids: string[];
  started_at: string;
  completed_at?: string | null;
  details: ImporterJobStatus[];
};

export type RecurringJob = {
  job_id: string | null;
  kind: string;
  repeat: boolean;
  interval?: number | null;
  started_at: string;
  runs: number;
  last_run_at?: string | null;
  last_job_ids: string[];
  options: Record<string, unknown>;
  history: JobRunSummary[];
};

export type ManualJobResult = {
  job_ids: string[];
  requested_at: string;
};

export type JobListing = {
  active: ImporterJobStatus[];
  recent: ImporterJobStatus[];
};

export type ConfigField = {
  key: string;
  type: 'string' | 'boolean' | 'integer';
  group: string;
  description: string;
  nullable: boolean;
  default: unknown;
  value: unknown;
};
