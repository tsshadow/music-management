import { writable } from 'svelte/store';

export const curatedPlaylists = writable([]);
export const currentPlaylist = writable(null);
export const currentTrack = writable(null);
export const isPlaying = writable(false);
export const view = writable('home'); // 'home', 'playlist', 'search'
