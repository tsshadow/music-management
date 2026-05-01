import { writable, derived } from 'svelte/store';

export const credentials = writable({
    url: window.location.origin,
    username: '',
    password: '',
});

export const currentTrack = writable(null);
export const playlist = writable([]);
export const playerState = writable({
    playing: false,
    volume: 50,
    progress: 0,
    duration: 0,
    shuffle: false,
    repeat: 'none', // 'none', 'one', 'all'
});

export const audio = writable(null);

export const authParams = derived(credentials, ($c) => {
    if (!$c.username || !$c.password) return '';
    return `u=${encodeURIComponent($c.username)}&p=${encodeURIComponent($c.password)}&v=1.12.0&c=spotify-ui&f=json`;
});
