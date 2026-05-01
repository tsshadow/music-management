import { writable } from 'svelte/store';

export const currentTrack = writable(null);
export const playerState = writable({
    playing: false,
    volume: 50,
    progress: 0,
    duration: 0
});
