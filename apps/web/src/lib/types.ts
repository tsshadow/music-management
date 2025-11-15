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
