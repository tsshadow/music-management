/**
 * Normalizes an artist string for comparison.
 * Splits by common separators, trims, and sorts alphabetically.
 *
 * @param {string} artist - The artist name or comma-separated list.
 * @returns {string} Normalized artist key.
 */
export function normalizeArtist(artist) {
    if (!artist) return "";
    // Separators: , & feat. ft. and (with optional spaces)
    const separators = /[,&]|\s+feat\.?\s+|\s+ft\.?\s+|\s+and\s+/i;
    return artist
        .split(separators)
        .map(a => a.trim().toLowerCase())
        .filter(a => a.length > 0)
        .sort()
        .join("|");
}

/**
 * Normalizes a title string for comparison.
 * Lowercases and trims.
 *
 * @param {string} title - The track title.
 * @returns {string} Normalized title key.
 */
export function normalizeTitle(title) {
    if (!title) return "";
    // Basic normalization
    let normalized = title.trim().toLowerCase();
    
    // Optional: strip metadata in parentheses if they don't contain version info
    // But the requirement says to keep version info for ranking.
    // So we'll keep it in the key too to distinguish "Radio Edit" from "Extended Mix" 
    // IF they are considered different versions.
    // The requirement says: "Tracks worden als duplicate beschouwd wanneer ze inhoudelijk dezelfde release/track lijken te zijn"
    // And: "Geef voorkeur aan Radio Edit boven Extended Mix"
    // This implies Radio Edit and Extended Mix ARE duplicates of each other.
    
    // To treat them as duplicates, we should strip them from the comparison key.
    normalized = normalized
        .replace(/\(radio edit\)/g, "")
        .replace(/radio edit/g, "")
        .replace(/\(extended mix\)/g, "")
        .replace(/extended mix/g, "")
        .replace(/\(original mix\)/g, "")
        .replace(/original mix/g, "")
        .trim();

    return normalized;
}

/**
 * Gets a ranking score for a track based on its quality and version.
 * Higher score is better.
 *
 * @param {Object} track - The track object.
 * @returns {number} The ranking score.
 */
export function getTrackScore(track) {
    let score = 0;

    // 1. Audio format/quality preference
    const suffix = (track.suffix || "").toLowerCase();
    const bitRate = track.bitRate || 0;

    if (suffix === 'flac') {
        score += 10000;
    } else if (suffix === 'mp3') {
        if (bitRate >= 320) score += 5000;
        else if (bitRate >= 192) score += 2000;
        else if (bitRate > 0) score += 1000;
    } else if (suffix === 'm4a' || suffix === 'aac') {
        score += 3000; // Somewhere in between
    }

    // 2. Version preference: Radio Edit > Original Mix > Extended Mix
    const title = (track.title || "").toLowerCase();
    if (title.includes("radio edit")) {
        score += 500;
    } else if (title.includes("extended mix")) {
        score += 100;
    } else if (title.includes("original mix")) {
        score += 300;
    } else {
        score += 200; // Default
    }

    return score;
}

/**
 * Generates a deduplication key for a track.
 *
 * @param {Object} track - The track object.
 * @returns {string} The deduplication key.
 */
export function getDeduplicateKey(track) {
    const artistKey = normalizeArtist(track.artist);
    const titleKey = normalizeTitle(track.title);
    return `${artistKey}:::${titleKey}`;
}

/**
 * Deduplicates an array of tracks, keeping the best version of each.
 *
 * @param {Object[]} tracks - Array of track objects.
 * @param {Map<string, Object>} [seenBefore] - Optional map of already seen tracks (key -> track).
 * @returns {Object[]} Deduplicated array of tracks.
 */
export function deduplicateTracks(tracks, seenBefore = new Map()) {
    const currentBatchBest = new Map();

    for (const track of tracks) {
        const key = getDeduplicateKey(track);
        
        // If we've already shown a version of this track in a previous batch, skip it.
        if (seenBefore.has(key)) {
            continue;
        }

        const existing = currentBatchBest.get(key);
        if (!existing || getTrackScore(track) > getTrackScore(existing)) {
            currentBatchBest.set(key, track);
        }
    }

    return Array.from(currentBatchBest.values());
}
