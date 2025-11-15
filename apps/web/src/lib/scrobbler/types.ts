/** Shared type definitions for scrobbler views and components. */
export interface HypePoint {
  label: string;
  value: number;
}

export interface LeaderboardRow {
  label: string;
  count: number;
  [key: string]: unknown;
}

export type ListenArtist = {
  id: number | null;
  name: string;
};

export type ListenRow = {
  id: number;
  listened_at: string;
  track_id: number;
  track_title: string;
  album_id: number | null;
  album_title: string | null;
  album_release_year: number | null;
  artists: ListenArtist[];
  artist_names: string | null;
  genres: string[];
  genre_names: string | null;
  source: string;
  source_track_id?: string | null;
  position_secs?: number | null;
  duration_secs?: number | null;
};
