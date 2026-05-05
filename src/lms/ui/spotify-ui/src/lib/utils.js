export function splitArtists(artistStr) {
    if (!artistStr) return [];
    return artistStr.split(', ').map(name => name.trim());
}

export function formatArtistList(artists) {
    if (artists.length <= 1) return artists[0] || '';
    const last = artists[artists.length - 1];
    const rest = artists.slice(0, artists.length - 1);
    return rest.join(', ') + ' and ' + last;
}
